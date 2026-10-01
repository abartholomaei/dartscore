import pytest

from dartscore.vision import board
from dartscore.vision.testset import SCENARIOS, parse_label


def test_every_scenario_spot_lies_in_its_target_field() -> None:
    for scenario in SCENARIOS:
        assert board.score_at(*scenario.spot_mm).label == scenario.target, scenario.id
        assert scenario.target in scenario.candidates, scenario.id


def test_scenario_ids_are_unique() -> None:
    assert len({s.id for s in SCENARIOS}) == len(SCENARIOS)


@pytest.mark.parametrize("text", ["T20", "s5", "D16", "25", "bull", "MISS"])
def test_labels_round_trip(text: str) -> None:
    assert parse_label(text).label == text.upper()


@pytest.mark.parametrize("text", ["T21", "X5", "", "50"])
def test_invalid_labels_are_refused(text: str) -> None:
    with pytest.raises(ValueError, match="not a field"):
        parse_label(text)
