import pytest

from dartscore.game import Dart, GameError, create_game
from dartscore.game.base import Game
from dartscore.game.stats import game_stats


def play(game: Game, *labels: str) -> None:
    for label in labels:
        if label == "NEXT":
            game.next_turn()
        else:
            game.throw(Dart.parse(label))


def test_around_the_clock_single() -> None:
    game = create_game("around_the_clock", 1, {"include_bull": False})
    play(game, "S1", "T2", "S5")  # 1 and 2 hit (any ring), 5 is not the target 3
    assert game.state()["position"] == [2]
    assert game.state()["current_targets"] == ["3"]
    for n in range(3, 21):
        play(game, "NEXT", f"S{n}")
    assert game.finished


def test_around_the_clock_doubles_and_skips() -> None:
    game = create_game("around_the_clock", 1, {"variant": "double"})
    play(game, "S1", "D1", "D2")
    assert game.state()["position"] == [2]
    skip = create_game("around_the_clock", 1, {"skip_multiples": True})
    play(skip, "T1")
    assert skip.state()["position"] == [3]


def test_shanghai_scores_and_winner_after_rounds() -> None:
    game = create_game("shanghai", 2, {"rounds": 2})
    play(game, "S1", "D1", "S5", "NEXT", "T1", "MISS", "MISS", "NEXT")  # round 1: 3 vs 3
    play(game, "D2", "MISS", "MISS", "NEXT", "S2", "MISS")
    assert not game.finished
    play(game, "MISS")
    assert game.finished
    assert game.winner == 0
    assert game.state()["scores"] == [7, 5]


def test_shanghai_instant_win() -> None:
    game = create_game("shanghai", 2, {"rounds": 7})
    play(game, "S1", "D1", "T1")
    assert game.finished
    assert game.winner == 0


def test_bobs_27() -> None:
    game = create_game("bobs_27", 1, {})
    play(game, "D1", "D1", "MISS")  # +2 +2
    assert game.state()["scores"] == [31]
    play(game, "NEXT", "S2", "MISS", "MISS")  # no double 2: -4
    assert game.state()["scores"] == [27]
    assert game.state()["target"] == "D3"
    # miss everything: 27 - 6 - 8 - 10 = 3, then -12 -> out
    for _ in range(4):
        play(game, "NEXT", "MISS", "MISS", "MISS")
    assert game.state()["out"] == [True]
    assert game.finished


def test_checkout_training_success_fail_and_bust() -> None:
    game = create_game(
        "checkout_training",
        1,
        {"count": 2, "min_score": 40, "max_score": 40, "darts_per_target": 3, "seed": 5},
    )
    assert game.state()["targets"] == [40, 40]
    play(game, "D20")  # checked out with the first dart: next target, turn ends
    assert game.state()["successes"] == [1]
    assert game.state()["awaiting_next"] is True
    play(game, "NEXT", "S20", "S20")  # 0 but no double: bust ends the turn
    assert game.state()["remaining"] == [40]
    play(game, "NEXT", "MISS")  # third dart on the target: failed
    assert game.finished
    assert game_stats(game)[0].score == 1


def test_doubles_training_hits_per_double() -> None:
    game = create_game("doubles_training", 1, {"include_bull": False})
    play(game, "D1", "S1", "D1")
    state = game.state()
    assert state["hits"] == [2]
    assert state["hits_by_target"] == [{"1": 2}]
    for _ in range(19):
        play(game, "NEXT", "MISS", "MISS", "MISS")
    assert game.finished
    stats = game_stats(game)[0]
    assert stats.hits == 2
    assert stats.darts == 60
    assert stats.hit_rate == pytest.approx(2 / 60, abs=1e-3)


def test_training_settings_are_validated() -> None:
    with pytest.raises(GameError):
        create_game("shanghai", 1, {"rounds": 30})
    with pytest.raises(GameError):
        create_game("checkout_training", 1, {"darts_per_target": 5})


def test_bull_off_closest_starts_and_ties_rethrow() -> None:
    game = create_game("bull_off", 3, {})
    play(game, "25", "NEXT", "25", "NEXT", "S5")  # tie between players 0 and 1
    assert not game.finished
    play(game, "NEXT", "T20", "NEXT", "BULL", "NEXT", "MISS")
    assert game.finished
    assert game.winner == 1
