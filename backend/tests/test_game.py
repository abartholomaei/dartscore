import pytest

from dartscore.game import Dart, GameError, create_game, replay_game
from dartscore.game.checkout import one_dart_finish, suggest_checkout
from dartscore.game.cricket import CricketGame
from dartscore.game.stats import game_stats
from dartscore.game.x01 import X01Game


def throw(game: object, *labels: str) -> None:
    assert isinstance(game, X01Game | CricketGame)
    for label in labels:
        if label == "NEXT":
            game.next_turn()
        else:
            game.throw(Dart.parse(label))


def x01(players: int = 2, **settings: object) -> X01Game:
    game = create_game("x01", players, {"start_score": 101, **settings})
    assert isinstance(game, X01Game)
    return game


# --- dart --------------------------------------------------------------------------------


def test_dart_parse_and_validate() -> None:
    assert Dart.parse("t20").points == 60
    assert Dart.parse("BULL").points == 50
    assert Dart.parse("25").points == 25
    assert Dart.parse("7") == Dart(7, 1)
    assert Dart.parse("MISS").is_miss
    with pytest.raises(ValueError, match="Invalid"):
        Dart(25, 3)
    with pytest.raises(ValueError, match="Invalid"):
        Dart(21, 1)


# --- checkout ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("remaining", "route"),
    [
        (170, "T20 T20 BULL"),
        (100, "T20 D20"),
        (50, "BULL"),
        (40, "D20"),
        (3, "S1 D1"),
    ],
)
def test_checkout_routes(remaining: int, route: str) -> None:
    result = suggest_checkout(remaining)
    assert result is not None
    assert " ".join(d.label for d in result) == route


def test_no_checkout_for_bogey_numbers_and_too_few_darts() -> None:
    for bogey in (169, 168, 166, 165, 163, 162, 159):
        assert suggest_checkout(bogey) is None
    assert suggest_checkout(1) is None
    assert suggest_checkout(100, darts_left=1) is None
    assert suggest_checkout(1, rule="single") is not None


def test_one_dart_finish() -> None:
    assert one_dart_finish(40, "double")
    assert not one_dart_finish(41, "double")
    assert one_dart_finish(50, "double")
    assert one_dart_finish(57, "master")


# --- X01 ---------------------------------------------------------------------------------


def test_x01_turns_and_checkout() -> None:
    game = x01()
    throw(game, "T20", "S1", "MISS")
    assert game.state()["remaining"] == [40, 101]
    assert game.state()["awaiting_next"] is True
    with pytest.raises(GameError) as exc:
        game.throw(Dart.parse("S1"))
    assert exc.value.code == "turn_closed"
    throw(game, "NEXT", "S20", "NEXT", "D20")
    assert game.finished
    assert game.winner == 0


def test_x01_bust_resets_turn() -> None:
    game = x01()
    throw(game, "T20", "S20", "NEXT", "S1", "NEXT")  # player 0 on 21
    throw(game, "T20")  # would leave -39: bust
    state = game.state()
    assert state["turn"]["bust"] is True
    assert state["remaining"][0] == 21


def test_x01_bust_on_one_and_on_single_finish() -> None:
    game = x01(players=1)
    throw(game, "T20", "T13", "NEXT")  # 101 - 99 = 2
    throw(game, "S1")  # leaves 1 -> bust with double out
    assert game.state()["remaining"] == [2]
    throw(game, "NEXT", "S2")  # zero but not a double -> bust
    assert game.state()["turn"]["bust"] is True
    throw(game, "NEXT", "D1")
    assert game.finished


def test_x01_single_out_and_double_in() -> None:
    game = x01(players=1, in_rule="double", out_rule="single")
    throw(game, "T20", "S20")  # not opened: no score
    assert game.state()["remaining"] == [101]
    throw(game, "D20")  # opens and counts
    assert game.state()["remaining"] == [61]
    throw(game, "NEXT", "T20", "S1")
    assert game.finished


def test_x01_implicit_misses_on_early_next() -> None:
    game = x01()
    throw(game, "T20", "NEXT")
    turn = game.legs[0].turns[0]
    assert [d.label for d in turn.darts] == ["T20", "MISS", "MISS"]
    assert turn.implicit_misses == 2
    assert game.current_player == 1


def test_x01_legs_sets_and_rotating_starter() -> None:
    game = x01(legs_to_win=2, sets_to_win=2)
    throw(game, "T20", "S1", "D20", "NEXT")  # leg 1 (set 1): player 0 wins, pulls darts
    assert game.legs_won == [1, 0]
    assert game.current_player == 1  # player 1 starts leg 2
    throw(game, "T20", "S1", "D20", "NEXT")  # leg 2: player 1 wins
    throw(game, "T20", "S1", "D20", "NEXT")  # leg 3: player 0 starts and wins -> set 1
    assert game.sets_won == [1, 0]
    assert game.legs_won == [0, 0]
    assert game.state()["set"] == 2
    throw(game, "T20", "S1", "D20")  # player 1 starts set 2, leg 1
    throw(game, "T20", "S1", "D20")  # next leg without pulling first: player 0 wins
    assert game.legs_won == [1, 1]


def test_x01_state_shows_winning_turn_until_next() -> None:
    game = x01()
    throw(game, "T20", "S1", "D20")
    state = game.state()
    assert state["leg_winner"] == 0
    assert state["turn"]["checkout"] is True
    assert state["legs_won"] == [1, 0]


def test_x01_undo_and_replace() -> None:
    game = x01()
    throw(game, "T20", "T20")  # 101 - 120: bust
    assert game.state()["turn"]["bust"] is True
    game.undo()
    assert game.state()["remaining"][0] == 41
    throw(game, "S1")
    game.replace_dart(-1, 1, Dart.parse("S20"))
    assert game.state()["remaining"][0] == 21
    with pytest.raises(GameError):
        game.replace_dart(5, 0, Dart.parse("S1"))


def test_x01_replace_dart_in_previous_turn() -> None:
    game = x01()
    throw(game, "S20", "S20", "S20", "NEXT", "S5", "S5", "S5", "NEXT")
    game.replace_dart(0, 2, Dart.parse("S1"))
    assert game.state()["remaining"] == [60, 86]


def test_replace_that_would_invalidate_later_events_is_rolled_back() -> None:
    game = x01()
    throw(game, "T20", "S1", "MISS", "NEXT", "S5", "S5", "S5", "NEXT", "S20")
    # turning the MISS into D20 would end the game before the later darts
    with pytest.raises(GameError) as exc:
        game.replace_dart(0, 2, Dart.parse("D20"))
    assert exc.value.code == "game_finished"
    assert game.state()["remaining"] == [20, 86]


def test_x01_checkout_suggestion_in_state() -> None:
    game = x01(players=1)
    throw(game, "S1")
    assert game.state()["checkout"] == ["T20", "D20"]


def test_replay_reproduces_state() -> None:
    game = x01(legs_to_win=2)
    throw(game, "T20", "S1", "D20", "NEXT", "S20", "S20", "S20", "NEXT")
    copy = replay_game("x01", 2, game.settings_dict(), game.events)
    assert copy.state() == game.state()


def test_invalid_settings() -> None:
    with pytest.raises(GameError) as exc:
        create_game("x01", 2, {"start_score": 123})
    assert exc.value.code == "invalid_settings"
    with pytest.raises(GameError):
        create_game("x01", 2, {"bogus": 1})
    with pytest.raises(GameError):
        create_game("golf", 2, {})
    with pytest.raises(GameError):
        create_game("x01", 0, {})


# --- Cricket -----------------------------------------------------------------------------


def cricket(players: int = 2, variant: str = "standard") -> CricketGame:
    game = create_game("cricket", players, {"variant": variant})
    assert isinstance(game, CricketGame)
    return game


def test_cricket_marks_and_points() -> None:
    game = cricket()
    throw(game, "T20", "S20", "D20")  # closes 20, then 3 extra marks = 60
    state = game.state()
    assert state["marks"][0][0] == 3
    assert state["points"] == [60, 0]
    throw(game, "NEXT", "T20", "S5", "MISS", "NEXT")  # player 1 closes 20
    throw(game, "S20")  # closed by everyone: no points
    assert game.state()["points"] == [60, 0]


def test_cricket_bull_marks() -> None:
    game = cricket()
    throw(game, "BULL", "25")
    assert game.state()["marks"][0][6] == 3


def test_cricket_win_requires_all_closed_and_lead() -> None:
    game = cricket(players=2)
    for target in ("20", "19", "18", "17", "16", "15"):
        throw(game, f"T{target}", "MISS", "MISS", "NEXT", "MISS", "MISS", "MISS", "NEXT")
    assert not game.finished
    throw(game, "BULL", "25")
    assert game.finished
    assert game.winner == 0


def test_cricket_cut_throat_gives_points_to_opponents() -> None:
    game = cricket(players=3, variant="cut_throat")
    throw(game, "T20", "T20")
    assert game.state()["points"] == [0, 60, 60]


def test_cricket_no_score() -> None:
    game = cricket(variant="no_score")
    throw(game, "T20", "T20")
    assert game.state()["points"] == [0, 0]


# --- stats -------------------------------------------------------------------------------


def test_x01_stats() -> None:
    game = x01(players=2)
    # player 0: 60, then checkout 41 with S1 D20 (2 darts), total 101 in 5 darts
    throw(game, "T20", "MISS", "MISS", "NEXT", "S5", "S5", "S5", "NEXT", "S1", "D20")
    p0, p1 = game_stats(game)
    assert p0.darts == 5
    assert p0.points == 101
    assert p0.average == pytest.approx(60.6)
    assert p0.checkouts == 1
    assert p0.checkout_attempts == 1  # only the D20 dart was thrown at a one-dart finish
    assert p0.highest_finish == 41
    assert p0.best_leg_darts == 5
    assert p0.tons["60"] == 1
    assert p0.won is True
    assert p1.points == 15
    assert p1.legs_played == 1
    assert p1.legs_won == 0


def test_cricket_mpr() -> None:
    game = cricket()
    throw(game, "T20", "S19", "MISS", "NEXT", "MISS", "MISS", "MISS", "NEXT")
    p0, p1 = game_stats(game)
    assert p0.marks == 4
    assert p0.mpr == 4.0
    assert p1.mpr == 0.0


def test_identical_turns_are_distinguished() -> None:
    # two turns with the same darts: correcting the second must not touch the first
    game = x01()
    throw(game, "S1", "S1", "S1", "NEXT", "S5", "S5", "S5", "NEXT", "S1", "S1", "S1")
    game.replace_dart(-1, 0, Dart.parse("S20"))
    assert [d.label for d in game.legs[0].turns[0].darts] == ["S1", "S1", "S1"]
    assert [d.label for d in game.legs[0].turns[2].darts] == ["S20", "S1", "S1"]


def test_checkout_prefers_favourite_double_with_same_dart_count() -> None:
    assert [d.label for d in suggest_checkout(64) or ()] == ["T16", "D8"]
    assert (suggest_checkout(64, preferred=16) or ())[-1].label == "D16"
    # one dart is better than two: 40 stays D20 even with D16 as favourite
    assert [d.label for d in suggest_checkout(40, preferred=16) or ()] == ["D20"]
