import pytest

from dartscore.game import Dart, GameError, create_game
from dartscore.game.base import Game


def play(game: Game, *labels: str) -> None:
    for label in labels:
        if label == "NEXT":
            game.next_turn()
        else:
            game.throw(Dart.parse(label))


def test_segment_training_counts_hits_until_the_dart_limit() -> None:
    game = create_game(
        "segment_training", 1, {"number": 20, "ring": "triple", "end": "darts", "limit": 33}
    )
    play(game, "T20", "S20", "T20", "NEXT")
    assert game.state()["hits"] == [2]
    assert game.state()["target"] == "T20"
    for _ in range(9):
        play(game, "MISS", "MISS", "MISS", "NEXT")
    play(game, "MISS", "MISS", "MISS")  # dart 33
    assert game.finished
    assert game.player_result(0) == {"score": 2, "hits": 2}


def test_segment_training_hits_mode_fewest_darts_wins() -> None:
    game = create_game(
        "segment_training", 2, {"number": 25, "ring": "any", "end": "hits", "limit": 2}
    )
    play(game, "25", "BULL", "NEXT")  # A done after 2 darts
    play(game, "25", "MISS", "MISS", "NEXT")
    assert game.current_player == 1  # A is skipped
    play(game, "BULL")
    assert game.winner == 0


def test_segment_training_random_targets_are_reproducible() -> None:
    a = create_game("segment_training", 1, {"number": 0, "seed": 5})
    b = create_game("segment_training", 1, {"number": 0, "seed": 5})
    assert a.state()["target"] == b.state()["target"]
    with pytest.raises(GameError):
        create_game("segment_training", 1, {"number": 25, "ring": "triple"})


def test_checkout_121_moves_up_and_down() -> None:
    game = create_game("checkout_121", 1, {"attempts": 3})
    play(game, "T20", "T17", "D5")  # 121 checked out -> 122
    assert game.state()["target_score"] == [122]
    game.next_turn()
    for _ in range(3):
        play(game, "MISS", "MISS", "MISS", "NEXT")  # 9 darts missed -> down again, not below 121
    assert game.state()["target_score"] == [121]
    play(game, "S20", "S20", "MISS", "NEXT")
    play(game, "MISS", "MISS", "MISS", "NEXT")
    play(game, "MISS", "MISS", "MISS")
    assert game.finished
    assert game.player_result(0) == {"score": 121, "hits": 1}
    assert game.state()["best"] == [121]
