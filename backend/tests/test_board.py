import pytest

from dartscore.vision.board import CALIBRATION_POINTS, Score, score_at, segment_at_angle


@pytest.mark.parametrize(
    ("x", "y", "label", "points"),
    [
        (0, 0, "BULL", 50),
        (0, 10, "25", 25),
        (0, 103, "T20", 60),
        (0, 166, "D20", 40),
        (0, 50, "S20", 20),
        (0, -103, "T3", 9),
        (103, 0, "T6", 18),
        (-103, 0, "T11", 33),
        (0, 171, "MISS", 0),
    ],
)
def test_score_at(x: float, y: float, label: str, points: int) -> None:
    score = score_at(x, y)
    assert score.label == label
    assert score.points == points


def test_segment_boundaries() -> None:
    # the 20 spans -9..9 degrees around the top (90 degrees)
    assert segment_at_angle(90 + 8.9) == 20
    assert segment_at_angle(90 + 9.1) == 5
    assert segment_at_angle(90 - 9.1) == 1


def test_score_labels() -> None:
    assert Score(19, 1).label == "S19"
    assert Score(0, 0).label == "MISS"


def test_calibration_points_lie_on_double_ring_or_center() -> None:
    for point in CALIBRATION_POINTS:
        r = (point.x_mm**2 + point.y_mm**2) ** 0.5
        assert r == pytest.approx(170.0) or point.id == "bull"
