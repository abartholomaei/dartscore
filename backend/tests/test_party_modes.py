import pytest

from dartscore.game import Dart, GameError, create_game
from dartscore.game.base import Game
from dartscore.game.party import HALVE_IT_TARGETS, KillerGame


def play(game: Game, *labels: str) -> None:
    for label in labels:
        if label == "NEXT":
            game.next_turn()
        else:
            game.throw(Dart.parse(label))


def killer(players: int = 3, **options: int) -> KillerGame:
    game = create_game("killer", players, {"seed": 7, **options})
    assert isinstance(game, KillerGame)
    return game


def test_killer_numbers_are_unique_and_reproducible() -> None:
    game = killer(4)
    assert len(set(game.numbers)) == 4
    assert killer(4).numbers == game.numbers
    assert game.state()["numbers"] == game.numbers


def test_killer_arm_then_take_lives() -> None:
    game = killer(2, lives=2)
    a, b = game.numbers
    play(game, f"D{b}", "MISS", "MISS", "NEXT")  # not a killer yet: no effect
    assert game.state()["lives"] == [2, 2]
    play(game, "MISS", "MISS", "MISS", "NEXT")
    play(game, f"D{a}", f"D{b}")
    assert game.state()["killer"] == [True, False]
    assert game.state()["lives"] == [2, 1]
    play(game, f"D{b}")
    assert game.winner == 0


def test_killer_own_double_costs_a_killer_a_life_and_dead_players_are_skipped() -> None:
    game = killer(3, lives=1)
    a, b, c = game.numbers
    play(game, f"D{a}", f"D{a}")  # armed, then hits own double: out
    assert game.state()["lives"][0] == 0
    game.next_turn()
    assert game.current_player == 1
    play(game, f"D{b}", f"D{c}")  # B kills C, last one standing
    assert game.winner == 1


def test_killer_needs_two_players() -> None:
    with pytest.raises(GameError):
        create_game("killer", 1, {})


def test_halve_it_scores_and_halves() -> None:
    game = create_game("halve_it", 1, {})
    play(game, "T20", "S20", "S1", "NEXT")  # 40 + 80
    assert game.state()["scores"] == [120]
    assert game.state()["target"] == "16"
    play(game, "S15", "MISS", "MISS", "NEXT")  # no 16: halved
    assert game.state()["scores"] == [60]
    assert game.state()["target"] == "D"
    play(game, "D3", "NEXT")
    assert game.state()["scores"] == [66]
    for _ in range(len(HALVE_IT_TARGETS) - 3):
        assert not game.finished
        play(game, "NEXT")
    assert game.finished
    assert game.player_result(0)["score"] == 66 // 2 ** (len(HALVE_IT_TARGETS) - 3)


def test_gotcha_resets_opponents_and_busts() -> None:
    game = create_game("gotcha", 2, {"target": 101})
    play(game, "T20", "NEXT")
    play(game, "S20", "S20", "S20")  # lands on 60: player 0 back to zero
    assert game.state()["scores"] == [0, 60]
    game.next_turn()
    play(game, "MISS", "NEXT", "T20")  # 120 > 101: bust
    assert game.state()["scores"] == [0, 60]
    game.next_turn()
    play(game, "NEXT", "T13", "S2")  # 60 + 41 = 101
    assert game.winner == 1


def test_score_training_sums_points_over_rounds() -> None:
    game = create_game("score_training", 1, {"rounds": 5})
    for _ in range(5):
        play(game, "T20", "T20", "T20")
        if not game.finished:
            game.next_turn()
    assert game.finished
    assert game.state()["scores"] == [900]
    with pytest.raises(GameError):
        create_game("score_training", 1, {"rounds": 7})


def test_bermuda_uses_its_own_sequence() -> None:
    from dartscore.game.party import BERMUDA_TARGETS

    game = create_game("halve_it", 1, {"targets": "bermuda", "start": 0})
    assert game.state()["target"] == "12"
    assert game.state()["rounds"] == len(BERMUDA_TARGETS)
    play(game, "S12", "T12", "MISS", "NEXT")
    assert game.state()["scores"] == [48]
    assert game.state()["target"] == "13"


def test_round_the_world_follows_the_board() -> None:
    game = create_game("around_the_clock", 1, {"order": "board", "include_bull": False})
    assert game.state()["current_targets"] == ["20"]
    play(game, "S20", "S1", "S2")  # 2 is not next on the board (18 is)
    assert game.state()["current_targets"] == ["18"]


def test_random_cricket_draws_six_numbers() -> None:
    game = create_game("cricket", 2, {"numbers": "random", "seed": 3})
    targets = game.state()["targets"]
    assert len(targets) == 7
    assert targets[-1] == 25
    assert targets[:6] == sorted(targets[:6], reverse=True)
    assert create_game("cricket", 2, {"numbers": "random", "seed": 3}).state()["targets"] == targets
    number = targets[0]
    play(game, f"T{number}")
    assert game.state()["marks"][0][0] == 3
