"""Exports recordings as a YOLO object detection dataset.

Every recording holds the camera images after a throw, the positions of all darts in the board
and the calibration the images were taken with. Projecting the dart positions through the
calibration gives the tip in every image, so no manual labeling is needed. Like DeepDarts,
keypoints are modelled as small boxes:

- class 0: dart tip
- classes 1-4: the four calibration points 20/1, 6/10, 3/19, 11/14 (auto calibration later)

Labels are checked against the game events: a dart the player corrected to another field has
an unknown position, so its images are left out (listed in ``needs_label.txt``).
"""

import json
import random
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from dartscore.vision import board

CLASSES = ["dart", "cal_20_1", "cal_6_10", "cal_3_19", "cal_11_14"]
CALIBRATION_IDS = ["20/1", "6/10", "3/19", "11/14"]
# box size around a keypoint, as a share of the image width
BOX_SIZE = 0.025


@dataclass
class ExportStats:
    recordings: int = 0
    images: int = 0
    skipped_unknown_darts: int = 0
    skipped_low_confidence: int = 0
    needs_label: list[str] = field(default_factory=list)


def _project(homography: list[list[float]], points: list[tuple[float, float]]) -> np.ndarray:
    h = np.array(homography, dtype=np.float64)
    pts = np.c_[np.array(points, dtype=np.float64).reshape(-1, 2), np.ones(len(points))]
    proj = pts @ h.T
    return np.asarray(proj[:, :2] / proj[:, 2:3], dtype=np.float64)


def _labels(meta: dict[str, Any], camera_id: str, width: int, height: int) -> list[str]:
    cal = meta["calibrations"][camera_id]
    lines = []
    box = BOX_SIZE
    darts = meta["board_darts"] or []
    cal_points = [
        (board.CALIBRATION_POINTS_BY_ID[i].x_mm, board.CALIBRATION_POINTS_BY_ID[i].y_mm)
        for i in CALIBRATION_IDS
    ]
    targets = [(0, p) for p in darts] + [(i + 1, p) for i, p in enumerate(cal_points)]
    pixels = _project(cal["homography"], [p for _, p in targets])
    for (cls, _), (x, y) in zip(targets, pixels, strict=True):
        if 0 <= x < width and 0 <= y < height:
            lines.append(
                f"{cls} {x / width:.6f} {y / height:.6f} {box:.6f} {box * width / height:.6f}"
            )
    return lines


def _corrected_away(session: Session | None, meta: dict[str, Any]) -> bool:
    """True if the player corrected this dart to a field its detected position is not in."""
    if session is None or meta.get("game_id") is None or meta.get("event_seq") is None:
        return False
    from dartscore.storage.models import GameEventRecord

    record = session.scalars(
        select(GameEventRecord).where(
            GameEventRecord.game_id == meta["game_id"], GameEventRecord.seq == meta["event_seq"]
        )
    ).first()
    if record is None or record.source != "corrected":
        return False
    det = meta["detection"]
    detected = board.score_at(det["x_mm"], det["y_mm"])
    return (detected.segment, detected.multiplier) != (record.segment, record.multiplier)


def export_dataset(
    recordings_dir: Path,
    out_dir: Path,
    session: Session | None = None,
    min_confidence: float = 0.5,
    val_share: float = 0.15,
    seed: int = 1,
) -> ExportStats:
    stats = ExportStats()
    metas = sorted(recordings_dir.rglob("meta.json"))
    # split by recording day so validation images come from other sessions than training ones
    days = sorted({m.parent.parent.name for m in metas})
    rng = random.Random(seed)
    val_days = (
        set(rng.sample(days, max(1, round(len(days) * val_share)))) if len(days) > 1 else set()
    )

    if out_dir.exists():
        shutil.rmtree(out_dir)
    for split in ("train", "val"):
        (out_dir / "images" / split).mkdir(parents=True)
        (out_dir / "labels" / split).mkdir(parents=True)

    for meta_path in metas:
        meta = json.loads(meta_path.read_text())
        stats.recordings += 1
        if meta.get("board_darts") is None or "calibrations" not in meta:
            stats.skipped_unknown_darts += 1
            continue
        if _corrected_away(session, meta):
            stats.needs_label.append(str(meta_path.parent))
            continue
        if (
            meta["detection"]["confidence"] < min_confidence
            and meta["detection"].get("accepted") is not True
        ):
            stats.skipped_low_confidence += 1
            continue
        split = "val" if meta_path.parent.parent.name in val_days else "train"
        for image_path in sorted(meta_path.parent.glob("*_after.jpg")):
            camera_id = image_path.name.removesuffix("_after.jpg")
            if camera_id not in meta["calibrations"]:
                continue
            image = cv2.imread(str(image_path))
            if image is None:
                continue
            h, w = image.shape[:2]
            name = f"{meta_path.parent.parent.name}_{meta_path.parent.name}_{camera_id}"
            shutil.copy2(image_path, out_dir / "images" / split / f"{name}.jpg")
            (out_dir / "labels" / split / f"{name}.txt").write_text(
                "\n".join(_labels(meta, camera_id, w, h)) + "\n"
            )
            stats.images += 1

    (out_dir / "data.yaml").write_text(
        f"path: {out_dir.resolve()}\ntrain: images/train\nval: images/val\n"
        + "names:\n"
        + "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASSES))
    )
    (out_dir / "needs_label.txt").write_text("\n".join(stats.needs_label) + "\n")
    return stats
