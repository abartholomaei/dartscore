"""Regression test on real throws recorded on the reference board (3 cameras, 2026-09-26).

The expected fields are the true results (corrected where the live detection was wrong).
Two of them were only detected correctly after tuning the tip search on real data:
164040 (tip part separated from the shaft) and 171315 (fragmented dart in two cameras).
"""

from pathlib import Path

import pytest

from dartscore.config import DetectionConfig
from dartscore.vision.replay import replay_recording

FIXTURES = Path(__file__).parent / "fixtures" / "recordings"


@pytest.mark.parametrize(
    ("recording", "expected"),
    [
        ("164040_069580", "D20"),
        ("171315_322895", "S5"),
        ("164102_141691", "MISS"),  # just outside the double ring
        ("164254_091449", "S20"),
    ],
)
def test_real_recording(recording: str, expected: str) -> None:
    label, hits = replay_recording(FIXTURES / recording, DetectionConfig())
    assert label == expected
    assert sum(h.used for h in hits) >= 2


@pytest.mark.parametrize(
    ("recording", "expected"),
    [
        ("164040_069580", "D20"),
        ("171315_322895", "S5"),
        ("164102_141691", "MISS"),
        ("164254_091449", "S20"),
    ],
)
def test_referee_agrees_on_real_throws(recording: str, expected: str) -> None:
    from dartscore.vision.referee import review_recording

    verdict = review_recording(FIXTURES / recording, DetectionConfig())
    assert verdict.label == expected
    assert len(verdict.cameras) == 3
    assert sum(c.used for c in verdict.cameras) >= 2
    assert all(c.found > 0 for c in verdict.cameras if c.used)


def test_uncertainty_rule_and_in_memory_review() -> None:
    import json

    import cv2

    from dartscore.vision.detection import CameraHit
    from dartscore.vision.referee import is_uncertain, review_images, review_recording

    agree = (CameraHit("a", (0, 0), (0.0, 110.0), 500), CameraHit("b", (0, 0), (1.0, 111.0), 500))
    assert not is_uncertain(agree)
    disagree = (CameraHit("a", (0, 0), (0.0, 103.0), 500), CameraHit("b", (0, 0), (0.0, 97.0), 500))
    assert is_uncertain(disagree)  # T20 vs S20
    assert is_uncertain(agree[:1])  # a single camera

    folder = FIXTURES / "164040_069580"
    meta = json.loads((folder / "meta.json").read_text())
    cams = meta["calibrations"]
    verdict = review_images(
        {c: cv2.imread(str(folder / f"{c}_before.jpg")) for c in cams},
        {c: cv2.imread(str(folder / f"{c}_after.jpg")) for c in cams},
        cams,
        DetectionConfig(),
    )
    assert verdict == review_recording(folder, DetectionConfig())
