"""Replays recorded detections with the current code and compares them with the truth.

The truth is the stored game event: a corrected dart holds what the player entered, an
uncorrected automatic dart is taken as right. Used to measure changes to the detection on real
throws instead of guessing (``dartscore replay``).
"""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from dartscore.config import DetectionConfig
from dartscore.game.dart import Dart
from dartscore.vision import board
from dartscore.vision.calibration import BoardCalibration
from dartscore.vision.detection import CameraHit, _roi_mask, find_dart_tip, fuse, local_resolution


@dataclass(frozen=True)
class ReplayResult:
    folder: str
    truth: str | None
    recorded: str
    replayed: str | None
    hits: tuple[CameraHit, ...]


def replay_recording(
    folder: Path,
    config: DetectionConfig,
    homographies: dict[str, NDArray[np.float64]] | None = None,
) -> tuple[str | None, tuple[CameraHit, ...]]:
    """``homographies`` replaces the recorded calibrations (to compare calibrations)."""
    meta = json.loads((folder / "meta.json").read_text())
    hits: list[CameraHit] = []
    for cid, cal_info in meta.get("calibrations", {}).items():
        before = cv2.imread(str(folder / f"{cid}_before.jpg"))
        after = cv2.imread(str(folder / f"{cid}_after.jpg"))
        if before is None or after is None:
            continue
        h, w = after.shape[:2]
        calibration = BoardCalibration(
            cid,
            {},
            homographies[cid]
            if homographies and cid in homographies
            else np.array(cal_info["homography"], dtype=np.float64),
            (w, h),
            bool(cal_info["undistorted"]),
            None,
            0.0,
        )
        mask = _roi_mask(calibration, (w, h), 1.0)
        min_px = max(20, int(config.min_dart_area * np.count_nonzero(mask) * 0.5))
        found = find_dart_tip(
            np.asarray(before, np.uint8),
            np.asarray(after, np.uint8),
            mask,
            config.pixel_threshold,
            min_px,
        )
        if found is None:
            continue
        (tx, ty), area = found
        bx, by = calibration.image_to_board(np.array([[tx, ty]]))[0]
        hits.append(
            CameraHit(
                cid,
                (round(tx, 1), round(ty, 1)),
                (round(float(bx), 1), round(float(by), 1)),
                area,
                mm_per_px=round(local_resolution(calibration, tx, ty), 2),
            )
        )
    if not hits:
        return None, ()
    x, y, _, marked = fuse(hits, config.max_spread_mm, len(meta.get("calibrations", {})))
    return board.score_at(x, y).label, tuple(marked)


def _truth(db: sqlite3.Connection | None, meta: dict[str, object]) -> str | None:
    if db is None or meta.get("game_id") is None or meta.get("event_seq") is None:
        return None
    row = db.execute(
        "select segment, multiplier, source from game_events "
        "where game_id = ? and seq = ? and kind = 'dart'",
        (meta["game_id"], meta["event_seq"]),
    ).fetchone()
    if row and row[2] == "bounce":
        # fell out of the board: the detected position was right, the score is not comparable
        return None
    return Dart(row[0], row[1]).label if row else None


def replay_all(
    recordings_dir: Path,
    database: Path | None,
    config: DetectionConfig,
    homographies: dict[str, NDArray[np.float64]] | None = None,
) -> list[ReplayResult]:
    db = (
        sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        if database and database.exists()
        else None
    )
    results = []
    try:
        for meta_path in sorted(recordings_dir.rglob("meta.json")):
            meta = json.loads(meta_path.read_text())
            if "calibrations" not in meta:
                continue
            replayed, hits = replay_recording(meta_path.parent, config, homographies)
            results.append(
                ReplayResult(
                    folder=f"{meta_path.parent.parent.name}/{meta_path.parent.name}",
                    truth=_truth(db, meta),
                    recorded=str(meta["detection"]["label"]),
                    replayed=replayed,
                    hits=hits,
                )
            )
    finally:
        if db is not None:
            db.close()
    return results
