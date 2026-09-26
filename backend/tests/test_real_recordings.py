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
