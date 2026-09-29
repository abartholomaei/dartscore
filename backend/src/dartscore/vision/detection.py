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

import math
from dataclasses import dataclass, field
from enum import StrEnum

import cv2
import numpy as np
from numpy.typing import NDArray

from dartscore.config import DetectionConfig
from dartscore.vision import board
from dartscore.vision.calibration import BoardCalibration
from dartscore.vision.intrinsics import Undistorter
from dartscore.vision.model import TipModel
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
    # board millimetres per image pixel at the tip: small = the camera sees this spot sharply
    mm_per_px: float = 1.0


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
    # the board right before the first dart of the turn: pulling all darts of the turn brings
    # it back, even when empty_small is stale (a missed takeout would otherwise never heal)
    turn_small: Gray | None = None
    # latest raw frame; its undistorted full-size version is computed only when needed
    last_raw: Image | None = None
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
    if diff.ndim == 2:
        return np.asarray(diff, dtype=np.uint8)
    # per-channel maximum with OpenCV: ~20x faster than numpy's max(axis=2)
    c0, c1, c2 = cv2.split(diff)
    return np.asarray(cv2.max(cv2.max(c0, c1), c2), dtype=np.uint8)


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

    Returns the tip (lowest point of the dart in the image) and the number of changed pixels
    belonging to the dart.
    """
    diff = color_diff(cv2.GaussianBlur(reference, (5, 5), 0), cv2.GaussianBlur(current, (5, 5), 0))
    _, binary = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    binary = cv2.bitwise_and(binary, mask)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    # A dart often falls apart into flight, shaft and barrel in the difference image (parts
    # that look like the background behind them). Darts stand upright in the image, so parts
    # are joined mostly vertically (measured on real throws: 15x61 px). The largest group is
    # kept, but the tip is taken from the original pixels of that group.
    joined = cv2.dilate(binary, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 61)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(joined)
    if count < 2:
        return None
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    ys, xs = np.nonzero((labels == largest) & (binary > 0))
    area = len(xs)
    if area < min_area_px:
        return None
    # The cameras look flat across the board and the dart sticks out towards them, so it
    # stands upright in the image with the tip at the bottom. The lowest point is robust;
    # a fitted axis gets pulled sideways by the large flight.
    bottom = ys.max()
    near_bottom = ys >= bottom - 3
    tip = (float(xs[near_bottom].mean()), float(bottom))
    return tip, area


def local_resolution(calibration: BoardCalibration, x: float, y: float) -> float:
    """Board millimetres covered by one image pixel at (x, y), in the worst direction."""
    pts = calibration.image_to_board(np.array([[x, y], [x + 1, y], [x, y + 1]]))
    return float(max(np.linalg.norm(pts[1] - pts[0]), np.linalg.norm(pts[2] - pts[0])))


def fuse(
    hits: list[CameraHit], max_spread_mm: float, camera_count: int
) -> tuple[float, float, float, list[CameraHit]]:
    """Combines the per-camera board positions.

    Each camera is trusted according to its local resolution: a camera seeing the spot from
    close by (few mm per pixel) counts more than one looking at it across the whole board.
    Two cameras agree if they are closer than ``max_spread_mm`` plus a margin for their
    resolution. The best supported group is averaged; if no cameras agree, the sharpest one
    wins. Returns x, y, confidence and the hits with the ignored ones marked as unused.
    """
    pts = np.array([h.board_mm for h in hits], dtype=np.float64)
    sigma = np.array([max(h.mm_per_px, 0.1) for h in hits])
    weight = 1.0 / sigma**2
    distances = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)
    tolerance = max_spread_mm + 3.0 * (sigma[:, None] + sigma[None, :])
    agrees = distances <= tolerance
    if agrees.sum(axis=1).max() == 1 and len(hits) > 2:
        # nobody agrees strictly: two cameras that are at least roughly together are still
        # more trustworthy than a single one far away from both (a wrong blob)
        agrees = distances <= 2 * tolerance
    count = agrees.sum(axis=1)
    support = (agrees * weight[None, :]).sum(axis=1)
    # more agreeing cameras first, then the sharper ones
    best = max(range(len(hits)), key=lambda i: (count[i], support[i], -sigma[i]))
    used_mask = agrees[best]
    marked = [
        CameraHit(h.camera_id, h.tip_px, h.board_mm, h.area_px, bool(u), h.mm_per_px)
        for h, u in zip(hits, used_mask, strict=True)
    ]
    w = weight[used_mask]
    x, y = (pts[used_mask] * w[:, None]).sum(axis=0) / w.sum()
    spread = float(np.max(np.linalg.norm(pts[used_mask] - [x, y], axis=1)))
    agreeing = int(used_mask.sum())
    confidence = (
        agreeing / max(camera_count, 1) * max(0.0, 1.0 - spread / (2 * max_spread_mm))
        if agreeing > 1
        else 0.3 / max(camera_count, 1)
    )
    return float(x), float(y), round(confidence, 3), marked


def refine_with_model(
    model: TipModel,
    calibration: BoardCalibration,
    image: Image,
    classic: tuple[tuple[float, float], int] | None,
    known_darts: list[tuple[float, float]],
) -> tuple[tuple[float, float], int] | None:
    """Prefers the model's tip for the new dart: model tips that are not one of the darts
    already in the board are candidates; the one nearest to the classic tip wins."""
    tips = model.tips(image)
    if not tips:
        return classic
    pixels = np.array([[k.x, k.y] for k in tips])
    board_pts = calibration.image_to_board(pixels)
    new = [
        (k, pt)
        for k, pt in zip(tips, board_pts, strict=True)
        if all(math.hypot(pt[0] - x, pt[1] - y) > 10.0 for x, y in known_darts)
    ]
    area = classic[1] if classic else 0
    if classic is not None:
        (cx, cy), _ = classic
        near = [(k, pt) for k, pt in new if math.hypot(k.x - cx, k.y - cy) < 40]
        if near:
            best = min(near, key=lambda item: math.hypot(item[0].x - cx, item[0].y - cy))[0]
            return (best.x, best.y), area
        return classic
    if len(new) == 1:
        return (new[0][0].x, new[0][0].y), area
    return None


@dataclass(frozen=True)
class CameraView:
    """One camera's view of a throw: the image after it and the classic tip (and its area)."""

    camera_id: str
    calibration: BoardCalibration
    image: Image
    classic: tuple[tuple[float, float], int] | None


def camera_hit(
    camera_id: str, calibration: BoardCalibration, found: tuple[tuple[float, float], int] | None
) -> CameraHit | None:
    if found is None:
        return None
    (tx, ty), area = found
    bx, by = calibration.image_to_board(np.array([[tx, ty]]))[0]
    return CameraHit(
        camera_id,
        (round(tx, 1), round(ty, 1)),
        (round(float(bx), 1), round(float(by), 1)),
        area,
        mm_per_px=round(local_resolution(calibration, tx, ty), 2),
    )


def locate(
    views: list[CameraView],
    config: DetectionConfig,
    camera_count: int,
    model: TipModel | None = None,
    known_darts: list[tuple[float, float]] | None = None,
) -> tuple[float, float, float, list[CameraHit]] | None:
    """Fuses the classic tips of all cameras. The model is only asked when that result is
    uncertain (confidence below ``model_below_confidence``); its tips win when they fuse to a
    more confident result."""

    def fused(hits: list[CameraHit | None]) -> tuple[float, float, float, list[CameraHit]] | None:
        found = [h for h in hits if h is not None]
        return fuse(found, config.max_spread_mm, camera_count) if found else None

    classic = fused([camera_hit(v.camera_id, v.calibration, v.classic) for v in views])
    if model is None or (classic is not None and classic[2] >= config.model_below_confidence):
        return classic
    refined = fused(
        [
            camera_hit(
                v.camera_id,
                v.calibration,
                refine_with_model(model, v.calibration, v.image, v.classic, known_darts or []),
            )
            for v in views
        ]
    )
    if refined is None or (classic is not None and refined[2] <= classic[2]):
        return classic
    return refined


class DartDetector:
    def __init__(
        self,
        config: DetectionConfig,
        calibrations: dict[str, BoardCalibration],
        undistorters: dict[str, Undistorter],
        model: TipModel | None = None,
    ) -> None:
        self.config = config
        self.model = model
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
        # positions (mm) of all darts believed to be in the board; None when unknown
        # (e.g. some darts were pulled) - used to label recorded images for training
        self.board_darts: list[tuple[float, float]] | None = []

    @property
    def camera_ids(self) -> list[str]:
        return list(self._cameras)

    def reset(self) -> None:
        """Forget all references (e.g. after the board was cleared manually)."""
        for cam in self._cameras.values():
            cam.ref_small = cam.ref_full = cam.empty_small = cam.prev_small = None
            cam.turn_small = None
        self.state = DetectorState.IDLE
        self.darts_in_turn = 0
        self._board_dirty = False
        self.board_darts = []

    def new_turn(self) -> None:
        """The game moved on manually. The empty reference is kept: darts still in the board
        are recognised as removed when they are pulled later."""
        self.darts_in_turn = 0

    def reference_images(self) -> dict[str, Image]:
        return {cid: c.ref_color for cid, c in self._cameras.items() if c.ref_color is not None}

    def calibration_info(self) -> dict[str, dict[str, object]]:
        """Calibrations in use, stored with recordings so images can be labeled later."""
        return {
            cid: {
                "homography": c.calibration.homography.tolist(),
                "undistorted": c.calibration.undistorted,
                "created_at": c.calibration.created_at,
            }
            for cid, c in self._cameras.items()
        }

    def previous_reference_images(self) -> dict[str, Image]:
        """The references before the last change (i.e. the board before the last dart)."""
        return {
            cid: c.prev_ref_color
            for cid, c in self._cameras.items()
            if c.prev_ref_color is not None
        }

    def current_images(self) -> dict[str, Image]:
        images = {cid: self._color(c) for cid, c in self._cameras.items()}
        return {cid: image for cid, image in images.items() if image is not None}

    def process(self, frames: dict[str, Image], now: float) -> list[DetectionEvent]:
        cfg = self.config
        moving = False
        for cid, cam in self._cameras.items():
            image = frames.get(cid)
            if image is None:
                continue
            # Undistorting every full frame of every camera is expensive; motion detection only
            # needs the small image, so that is undistorted after downscaling.
            self._prepare(cam, image)
            small = self._small(cam, image)
            cam.last_raw = image
            cam.last_color = None  # undistorted lazily, see _color
            cam.last_full = None  # computed lazily when needed
            if cam.ref_small is None:
                color = self._color(cam)
                assert color is not None
                self._set_reference(cam, color, small, empty=True)
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
        if self.state == DetectorState.BLOCKED and now - self._last_motion > cfg.blocked_timeout:
            # nothing moves but the view differs for good (light changed, board cleared by
            # hand): start over with the current view as the empty board
            self._absorb_current(empty=True)
            self._board_dirty = False
            self.darts_in_turn = 0
            self.board_darts = []
            self.state = DetectorState.IDLE
            self.last_evaluation = Evaluation({}, "recovered")
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

    def _color(self, cam: _Camera) -> Image | None:
        """The latest frame at full size, undistorted if the camera has a lens calibration."""
        if cam.last_color is None and cam.last_raw is not None:
            cam.last_color = (
                cam.undistorter.undistort(cam.last_raw) if cam.undistorter else cam.last_raw
            )
        return cam.last_color

    def _small(self, cam: _Camera, image: Image) -> Gray:
        # colors are kept: see color_diff
        small = np.asarray(image, dtype=np.uint8)
        if cam.scale < 1.0:
            small = np.asarray(
                cv2.resize(small, None, fx=cam.scale, fy=cam.scale, interpolation=cv2.INTER_AREA),
                dtype=np.uint8,
            )
        if cam.undistorter is not None:
            small = np.asarray(cam.undistorter.undistort(small), dtype=np.uint8)
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
        turn_areas: dict[str, float] = {}
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
            if cam.turn_small is not None and self.darts_in_turn > 0:
                differs_from_turn = (color_diff(cam.turn_small, cur) > th) & roi
                turn_areas[cid] = float(np.count_nonzero(differs_from_turn)) / cam.roi_pixels_small
        if not areas:
            return []

        big = [cid for cid, a in areas.items() if a > cfg.max_dart_area]
        dart_sized = [
            cid for cid, a in areas.items() if cfg.min_dart_area <= a <= cfg.max_dart_area
        ]
        board_empty = bool(empty_areas) and all(a < cfg.min_dart_area for a in empty_areas.values())
        # all darts of this turn gone again: as good as empty (and heals a stale empty board)
        back_to_turn_start = len(turn_areas) == len(areas) and all(
            a < cfg.min_dart_area for a in turn_areas.values()
        )

        # the board looks like at the start of the turn: darts were pulled
        if board_empty or back_to_turn_start:
            was_dirty = self._board_dirty or back_to_turn_start
            for cam in self._cameras.values():
                cam.turn_small = None
            self._absorb_current(empty=True)
            self._board_dirty = False
            self.darts_in_turn = 0
            self.board_darts = []
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
            self.board_darts = None
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
        if detection is not None and self.darts_in_turn == 0:
            for cam in self._cameras.values():
                cam.turn_small = cam.ref_small
        self._absorb_current(empty=False)
        self.state = DetectorState.IDLE
        self.last_evaluation = Evaluation(areas, "dart" if detection else "unlocated")
        if detection is None:
            # something dart-sized appeared that could not be located: positions are unknown
            self.board_darts = None
            return []
        self.darts_in_turn += 1
        if self.board_darts is not None:
            self.board_darts.append((detection.x_mm, detection.y_mm))
        return [detection]

    def _absorb_current(self, empty: bool) -> None:
        for cam in self._cameras.values():
            color = self._color(cam)
            if color is not None and cam.prev_small is not None:
                self._set_reference(cam, color, cam.prev_small, empty=empty)

    def _locate(self, camera_ids: list[str]) -> DartDetection | None:
        cfg = self.config
        views: list[CameraView] = []
        for cid in camera_ids:
            cam = self._cameras[cid]
            color = self._color(cam)
            if cam.ref_full is None or color is None or cam.mask_full is None:
                continue
            current = np.asarray(color, dtype=np.uint8)
            min_px = int(cfg.min_dart_area * cam.roi_pixels_small / (cam.scale**2) * 0.5)
            found = find_dart_tip(
                cam.ref_full, current, cam.mask_full, cfg.pixel_threshold, max(20, min_px)
            )
            views.append(CameraView(cid, cam.calibration, current, found))
        located = locate(views, cfg, len(self._cameras), self.model, self.board_darts or [])
        if located is None:
            return None
        x, y, confidence, marked = located
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
