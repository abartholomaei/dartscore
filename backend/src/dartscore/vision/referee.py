"""Referee: a slower, more thorough second look at a recorded dart.

Live detection uses one difference threshold per camera and has to be fast. The referee
re-evaluates the recorded before/after images with several thresholds per camera, takes the
median tip per camera (robust against a single noisy mask) and fuses the cameras again. It
reports what every camera saw, so a disputed dart can be decided with the photos in view.
"""

import json
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from dartscore.config import DetectionConfig
from dartscore.vision import board
from dartscore.vision.calibration import BoardCalibration
from dartscore.vision.detection import (
    CameraHit,
    _roi_mask,
    find_dart_tip,
    fuse,
    local_resolution,
    refine_with_model,
)
from dartscore.vision.model import TipModel
from dartscore.vision.sources import Image

# offsets to the configured difference threshold that are tried per camera; only equal or
# more sensitive ones: a stricter threshold loses the thin tip and moves it up the dart
THRESHOLD_STEPS = (-12, -8, -4, 0)


@dataclass(frozen=True)
class CameraVerdict:
    camera_id: str
    label: str | None
    board_mm: tuple[float, float] | None
    tip_px: tuple[float, float] | None
    # how many threshold variants found a dart
    found: int
    used: bool


@dataclass(frozen=True)
class Verdict:
    label: str | None
    x_mm: float | None
    y_mm: float | None
    cameras: tuple[CameraVerdict, ...]
    # all cameras that found the dart name the same field
    unanimous: bool


def review_recording(
    folder: Path, config: DetectionConfig, model: TipModel | None = None
) -> Verdict:
    meta = json.loads((folder / "meta.json").read_text())
    calibrations = meta.get("calibrations", {})
    befores = {cid: cv2.imread(str(folder / f"{cid}_before.jpg")) for cid in calibrations}
    afters = {cid: cv2.imread(str(folder / f"{cid}_after.jpg")) for cid in calibrations}
    known = [(float(p[0]), float(p[1])) for p in (meta.get("board_darts") or [])[:-1]]
    return review_images(befores, afters, calibrations, config, model, known)


def is_uncertain(hits: tuple[CameraHit, ...]) -> bool:
    """The live result deserves a second look: the cameras it was fused from name different
    fields, or only one camera saw the dart. On 606 real throws, re-checking exactly these
    (~30 %) gave the best result (596 vs 593 right; checking every dart: 595)."""
    used = [h for h in hits if h.used]
    return len(used) < 2 or len({board.score_at(*h.board_mm).label for h in used}) > 1


def review_images(
    befores: Mapping[str, Image | None],
    afters: Mapping[str, Image | None],
    calibrations: Mapping[str, Mapping[str, Any]],
    config: DetectionConfig,
    model: TipModel | None = None,
    known: list[tuple[float, float]] | None = None,
) -> Verdict:
    """The referee on in-memory images (live) or loaded recordings: ``calibrations`` as in
    the recording meta (homography, undistorted)."""
    known = known or []
    per_camera: list[tuple[str, CameraHit | None, int]] = []
    for cid, cal_info in calibrations.items():
        before = befores.get(cid)
        after = afters.get(cid)
        if before is None or after is None:
            per_camera.append((cid, None, 0))
            continue
        h, w = after.shape[:2]
        calibration = BoardCalibration(
            cid,
            {},
            np.array(cal_info["homography"], dtype=np.float64),
            (w, h),
            bool(cal_info["undistorted"]),
            None,
            0.0,
        )
        mask = _roi_mask(calibration, (w, h), 1.0)
        min_px = max(20, int(config.min_dart_area * np.count_nonzero(mask) * 0.5))
        tips: list[tuple[float, float]] = []
        areas: list[int] = []
        for step in THRESHOLD_STEPS:
            threshold = max(5, config.pixel_threshold + step)
            found = find_dart_tip(
                np.asarray(before, np.uint8), np.asarray(after, np.uint8), mask, threshold, min_px
            )
            if model is not None:
                found = refine_with_model(model, calibration, after, found, known)
            if found is not None:
                tips.append(found[0])
                areas.append(found[1])
        if not tips:
            per_camera.append((cid, None, 0))
            continue
        tx = statistics.median(t[0] for t in tips)
        ty = statistics.median(t[1] for t in tips)
        bx, by = calibration.image_to_board(np.array([[tx, ty]]))[0]
        hit = CameraHit(
            cid,
            (round(tx, 1), round(ty, 1)),
            (round(float(bx), 1), round(float(by), 1)),
            int(statistics.median(areas)),
            mm_per_px=round(local_resolution(calibration, tx, ty), 2),
        )
        per_camera.append((cid, hit, len(tips)))

    hits = [hit for _, hit, _ in per_camera if hit is not None]
    if not hits:
        return Verdict(
            None, None, None, tuple(_verdict(c, None, 0, False) for c, _, _ in per_camera), False
        )
    x, y, _, marked = fuse(hits, config.max_spread_mm, len(calibrations))
    used = {h.camera_id for h in marked if h.used}
    cameras = tuple(_verdict(cid, hit, n, cid in used) for cid, hit, n in per_camera)
    labels = {c.label for c in cameras if c.label is not None}
    return Verdict(
        board.score_at(x, y).label,
        round(x, 1),
        round(y, 1),
        cameras,
        unanimous=len(labels) == 1,
    )


def _verdict(cid: str, hit: CameraHit | None, found: int, used: bool) -> CameraVerdict:
    if hit is None:
        return CameraVerdict(cid, None, None, None, found, False)
    return CameraVerdict(
        cid, board.score_at(*hit.board_mm).label, hit.board_mm, hit.tip_px, found, used
    )
