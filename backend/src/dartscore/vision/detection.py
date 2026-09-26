"""Dart detection with classic image processing.

Pipeline per analysis step (all calibrated cameras together):

1. Motion: compare each camera frame with the previous one (downscaled).
2. Settle: once nothing moves for ``settle_time``, compare the frame with the reference image
   taken before the throw.
3. Classify the change per camera by its size: nothing / a dart / something big (hand, person).
4. Dart: find the dart in the full resolution difference image, take its tip (the end that
   touches the board, i.e. the lowest point in the image), map it onto the board with the
   calibration and fuse all cameras (median, outliers dropped).
5. Something big: wait until the board is back to the empty reference of the turn, which means
   the darts were pulled -> takeout (next player).

The engine has no threads and no clock of its own, so it can be driven by recorded frames.
"""

from dataclasses import dataclass, field
from enum import StrEnum

import cv2
import numpy as np
from numpy.typing import NDArray

from dartscore.config import DetectionConfig
from dartscore.vision import board
from dartscore.vision.calibration import BoardCalibration
from dartscore.vision.intrinsics import Undistorter
from dartscore.vision.sources import Image

Gray = NDArray[np.uint8]
# the ROI extends beyond the board edge a bit: darts stick out of the board towards the camera
ROI_RADIUS_MM = board.R_BOARD * 1.15


class DetectorState(StrEnum):
    IDLE = "idle"
    MOTION = "motion"
    # something big is in view (hand, person, darts being pulled)
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CameraHit:
    camera_id: str
    # tip in image pixels (calibration image space) and on the board (mm)
    tip_px: tuple[float, float]
    board_mm: tuple[float, float]
    area_px: int
    used: bool = True


@dataclass(frozen=True)
class DartDetection:
    x_mm: float
    y_mm: float
    label: str
    segment: int
    multiplier: int
    confidence: float
    hits: tuple[CameraHit, ...]


@dataclass(frozen=True)
class Takeout:
    pass


DetectionEvent = DartDetection | Takeout


@dataclass
class _Camera:
    calibration: BoardCalibration
    undistorter: Undistorter | None
    scale: float = 1.0
    mask_small: Gray | None = None
    mask_full: Gray | None = None
    roi_pixels_small: int = 1
    prev_small: Gray | None = None
    ref_small: Gray | None = None
    ref_full: Gray | None = None
    ref_color: Image | None = None
    prev_ref_color: Image | None = None
    empty_small: Gray | None = None
    last_color: Image | None = None
    last_full: Gray | None = None


@dataclass
class Evaluation:
    """What the last settled change looked like (for status display and recording)."""

    areas: dict[str, float] = field(default_factory=dict)
    kind: str = ""


def _roi_mask(calibration: BoardCalibration, size: tuple[int, int], scale: float) -> Gray:
    angles = np.linspace(0, 2 * np.pi, 180, endpoint=False)
    circle = np.stack([np.cos(angles), np.sin(angles)], axis=1) * ROI_RADIUS_MM
    pts = calibration.board_to_image(circle) * scale
    mask = np.zeros((size[1], size[0]), np.uint8)
    cv2.fillPoly(mask, [np.round(pts).astype(np.int32)], 255)
    return mask


def color_diff(a: Image, b: Image) -> Gray:
    """Per-pixel difference, taking the largest change over the color channels: a grey dart on
    a green field hardly differs in brightness but clearly in color."""
    diff = cv2.absdiff(a, b)
    return np.asarray(diff.max(axis=2) if diff.ndim == 3 else diff, dtype=np.uint8)


def _gray(image: Image) -> Gray:
    return np.asarray(
        cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image, dtype=np.uint8
    )


def _changed_fraction(a: Gray, b: Gray, mask: Gray, threshold: int, roi_pixels: int) -> float:
    diff = color_diff(a, b)
    changed = cv2.bitwise_and((diff > threshold).astype(np.uint8), (mask > 0).astype(np.uint8))
    return float(np.count_nonzero(changed)) / roi_pixels


def find_dart_tip(
    reference: Gray, current: Gray, mask: Gray, threshold: int, min_area_px: int
) -> tuple[tuple[float, float], int] | None:
    """Locates a new dart in the difference of two full resolution images.

    Returns the tip (lowest end of the dart along its main axis) and the blob area.
    """
    diff = color_diff(cv2.GaussianBlur(reference, (5, 5), 0), cv2.GaussianBlur(current, (5, 5), 0))
    _, binary = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    binary = cv2.bitwise_and(binary, mask)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    blob = max(contours, key=cv2.contourArea)
    area = int(cv2.contourArea(blob))
    if area < min_area_px:
        return None
    points = blob.reshape(-1, 2).astype(np.float64)
    vx, vy, x0, y0 = (float(v) for v in cv2.fitLine(points, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel())
    # orient the axis downwards: the tip is the end closest to the board surface
    if vy < 0:
        vx, vy = -vx, -vy
    along = (points[:, 0] - x0) * vx + (points[:, 1] - y0) * vy
    # the tip is thin: average the few outermost points instead of taking a single pixel
    far = points[along >= along.max() - 2.0]
    tip = far.mean(axis=0)
    return (float(tip[0]), float(tip[1])), area


def fuse(
    hits: list[CameraHit], max_spread_mm: float, camera_count: int
) -> tuple[float, float, float, list[CameraHit]]:
    """Combines the per-camera board positions: the largest group of cameras that agree
    within ``max_spread_mm`` wins; if none agree, the camera seeing most of the dart.
    Returns x, y, confidence and the hits with the ignored ones marked as unused."""
    pts = np.array([h.board_mm for h in hits], dtype=np.float64)
    distances = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)
    neighbours = (distances <= max_spread_mm).sum(axis=1)
    # most neighbours first, then the largest visible dart
    best = max(range(len(hits)), key=lambda i: (neighbours[i], hits[i].area_px))
    used_mask = distances[best] <= max_spread_mm
    marked = [
        CameraHit(h.camera_id, h.tip_px, h.board_mm, h.area_px, used=bool(u))
        for h, u in zip(hits, used_mask, strict=True)
    ]
    x, y = pts[used_mask].mean(axis=0)
    spread = float(np.max(np.linalg.norm(pts[used_mask] - [x, y], axis=1)))
    agreeing = int(used_mask.sum())
    confidence = (
        agreeing / max(camera_count, 1) * max(0.0, 1.0 - spread / (2 * max_spread_mm))
        if agreeing > 1
        else 0.3 / max(camera_count, 1)
    )
    return float(x), float(y), round(confidence, 3), marked


class DartDetector:
    def __init__(
        self,
        config: DetectionConfig,
        calibrations: dict[str, BoardCalibration],
        undistorters: dict[str, Undistorter],
    ) -> None:
        self.config = config
        self.state = DetectorState.IDLE
        self.darts_in_turn = 0
        self.last_evaluation = Evaluation()
        self._cameras = {
            cid: _Camera(cal, undistorters.get(cid) if cal.undistorted else None)
            for cid, cal in calibrations.items()
        }
        self._last_motion = 0.0
        # the board differed from the empty reference since the last takeout
        self._board_dirty = False

    @property
    def camera_ids(self) -> list[str]:
        return list(self._cameras)

    def reset(self) -> None:
        """Forget all references (e.g. after the board was cleared manually)."""
        for cam in self._cameras.values():
            cam.ref_small = cam.ref_full = cam.empty_small = cam.prev_small = None
        self.state = DetectorState.IDLE
        self.darts_in_turn = 0
        self._board_dirty = False

    def new_turn(self) -> None:
        """The game moved on manually. The empty reference is kept: darts still in the board
        are recognised as removed when they are pulled later."""
        self.darts_in_turn = 0

    def reference_images(self) -> dict[str, Image]:
        return {cid: c.ref_color for cid, c in self._cameras.items() if c.ref_color is not None}

    def previous_reference_images(self) -> dict[str, Image]:
        """The references before the last change (i.e. the board before the last dart)."""
        return {
            cid: c.prev_ref_color
            for cid, c in self._cameras.items()
            if c.prev_ref_color is not None
        }

    def current_images(self) -> dict[str, Image]:
        return {cid: c.last_color for cid, c in self._cameras.items() if c.last_color is not None}

    def process(self, frames: dict[str, Image], now: float) -> list[DetectionEvent]:
        cfg = self.config
        moving = False
        for cid, cam in self._cameras.items():
            image = frames.get(cid)
            if image is None:
                continue
            if cam.undistorter is not None:
                image = cam.undistorter.undistort(image)
            self._prepare(cam, image)
            small = self._small(cam, image)
            cam.last_color = image
            cam.last_full = None  # computed lazily when needed
            if cam.ref_small is None:
                self._set_reference(cam, image, small, empty=True)
            if cam.prev_small is not None and cam.mask_small is not None:
                motion = _changed_fraction(
                    cam.prev_small, small, cam.mask_small, cfg.pixel_threshold, cam.roi_pixels_small
                )
                moving = moving or motion > cfg.motion_area
            cam.prev_small = small

        if moving:
            self._last_motion = now
            if self.state == DetectorState.IDLE:
                self.state = DetectorState.MOTION
            return []
        if self.state == DetectorState.IDLE or now - self._last_motion < cfg.settle_time:
            return []
        return self._evaluate()

    # --- internals ----------------------------------------------------------------------

    def _prepare(self, cam: _Camera, image: Image) -> None:
        if cam.mask_small is not None:
            return
        h, w = image.shape[:2]
        cam.scale = min(1.0, self.config.analysis_width / w)
        small_size = (round(w * cam.scale), round(h * cam.scale))
        cam.mask_small = _roi_mask(cam.calibration, small_size, cam.scale)
        cam.mask_full = _roi_mask(cam.calibration, (w, h), 1.0)
        cam.roi_pixels_small = max(1, int(np.count_nonzero(cam.mask_small)))

    def _small(self, cam: _Camera, image: Image) -> Gray:
        # colors are kept: see color_diff
        small = np.asarray(image, dtype=np.uint8)
        if cam.scale < 1.0:
            small = np.asarray(
                cv2.resize(small, None, fx=cam.scale, fy=cam.scale, interpolation=cv2.INTER_AREA),
                dtype=np.uint8,
            )
        return np.asarray(cv2.GaussianBlur(small, (5, 5), 0), dtype=np.uint8)

    def _set_reference(self, cam: _Camera, image: Image, small: Gray, empty: bool = False) -> None:
        cam.prev_ref_color = cam.ref_color
        cam.ref_small = small
        cam.ref_full = np.asarray(image, dtype=np.uint8)
        cam.ref_color = image
        if empty:
            cam.empty_small = small.copy()

    def _evaluate(self) -> list[DetectionEvent]:
        cfg = self.config
        areas: dict[str, float] = {}
        empty_areas: dict[str, float] = {}
        removal: dict[str, float] = {}
        for cid, cam in self._cameras.items():
            if cam.prev_small is None or cam.ref_small is None or cam.mask_small is None:
                continue
            cur, th = cam.prev_small, cfg.pixel_threshold
            roi = cam.mask_small > 0
            changed = (color_diff(cam.ref_small, cur) > th) & roi
            areas[cid] = float(np.count_nonzero(changed)) / cam.roi_pixels_small
            if cam.empty_small is not None:
                differs_from_empty = (color_diff(cam.empty_small, cur) > th) & roi
                empty_areas[cid] = (
                    float(np.count_nonzero(differs_from_empty)) / cam.roi_pixels_small
                )
                # share of the change where the board looks empty again: something was removed
                n_changed = np.count_nonzero(changed)
                if n_changed:
                    removal[cid] = (
                        float(np.count_nonzero(changed & ~differs_from_empty)) / n_changed
                    )
        if not areas:
            return []

        big = [cid for cid, a in areas.items() if a > cfg.max_dart_area]
        dart_sized = [
            cid for cid, a in areas.items() if cfg.min_dart_area <= a <= cfg.max_dart_area
        ]
        board_empty = bool(empty_areas) and all(a < cfg.min_dart_area for a in empty_areas.values())

        # the board looks like at the start of the turn: darts were pulled
        if board_empty:
            was_dirty = self._board_dirty
            self._absorb_current(empty=True)
            self._board_dirty = False
            self.darts_in_turn = 0
            self.state = DetectorState.IDLE
            self.last_evaluation = Evaluation(areas, "takeout" if was_dirty else "nothing")
            return [Takeout()] if was_dirty else []
        self._board_dirty = True

        # something big in view (hand, person): wait until it is gone
        if len(big) * 2 > len(areas):
            self.state = DetectorState.BLOCKED
            self.last_evaluation = Evaluation(areas, "blocked")
            return []

        if not dart_sized:
            # bounce-out, light flicker, a dart outside the view: nothing to score. Without darts
            # in this turn the change is slow drift (light), so the empty reference follows it.
            refresh_empty = self.darts_in_turn == 0
            self._absorb_current(empty=refresh_empty)
            if refresh_empty:
                self._board_dirty = False
            self.state = DetectorState.IDLE
            self.last_evaluation = Evaluation(areas, "nothing")
            return []

        # darts pulled one by one: the changed spots look like the empty board again
        ratios = [removal[c] for c in dart_sized if c in removal]
        if ratios and float(np.median(ratios)) > 0.6:
            self._absorb_current(empty=False)
            self.state = DetectorState.BLOCKED
            self.last_evaluation = Evaluation(areas, "removal")
            return []

        if self.darts_in_turn >= 3:
            # a fourth "dart" is most likely a hand or a dart being moved
            self._absorb_current(empty=False)
            self.state = DetectorState.IDLE
            self.last_evaluation = Evaluation(areas, "ignored")
            return []

        detection = self._locate(dart_sized)
        self._absorb_current(empty=False)
        self.state = DetectorState.IDLE
        self.last_evaluation = Evaluation(areas, "dart" if detection else "unlocated")
        if detection is None:
            return []
        self.darts_in_turn += 1
        return [detection]

    def _absorb_current(self, empty: bool) -> None:
        for cam in self._cameras.values():
            if cam.last_color is not None and cam.prev_small is not None:
                self._set_reference(cam, cam.last_color, cam.prev_small, empty=empty)

    def _locate(self, camera_ids: list[str]) -> DartDetection | None:
        cfg = self.config
        hits: list[CameraHit] = []
        for cid in camera_ids:
            cam = self._cameras[cid]
            if cam.ref_full is None or cam.last_color is None or cam.mask_full is None:
                continue
            current = np.asarray(cam.last_color, dtype=np.uint8)
            min_px = int(cfg.min_dart_area * cam.roi_pixels_small / (cam.scale**2) * 0.5)
            found = find_dart_tip(
                cam.ref_full, current, cam.mask_full, cfg.pixel_threshold, max(20, min_px)
            )
            if found is None:
                continue
            (tx, ty), area = found
            bx, by = cam.calibration.image_to_board(np.array([[tx, ty]]))[0]
            hits.append(
                CameraHit(
                    cid,
                    (round(tx, 1), round(ty, 1)),
                    (round(float(bx), 1), round(float(by), 1)),
                    area,
                )
            )
        if not hits:
            return None
        x, y, confidence, marked = fuse(hits, cfg.max_spread_mm, len(self._cameras))
        score = board.score_at(x, y)
        return DartDetection(
            x_mm=round(x, 1),
            y_mm=round(y, 1),
            label=score.label,
            segment=score.segment,
            multiplier=score.multiplier,
            confidence=confidence,
            hits=tuple(marked),
        )
