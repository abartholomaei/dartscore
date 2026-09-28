import math
from pathlib import Path
from typing import Any

from dartscore.game import Dart, create_game
from dartscore.game.arcade import FruitSamuraiGame, MonsterHuntGame

OFF = (300.0, 300.0)  # far off the board


def hunt(players: int = 1, **settings: object) -> MonsterHuntGame:
    game = create_game("monster_hunt", players, {"seed": 11, "rounds": 5, **settings})
    assert isinstance(game, MonsterHuntGame)
    return game


def active(game: MonsterHuntGame) -> dict[str, Any]:
    return next(m for m in game.state()["monsters"] if m["status"] == "active")


def graze(monster: dict[str, Any]) -> tuple[float, float]:
    """A spot inside the monster but outside its headshot zone."""
    return (monster["x"] + monster["radius"] * 0.9, monster["y"])


def test_one_monster_at_a_time_and_the_same_for_every_player() -> None:
    game = hunt(2)
    first = game.state()["monsters"]
    assert [m["status"] for m in first] == ["active", "waiting", "waiting"]
    game.throw(Dart.miss(), OFF)
    game.next_turn()
    assert game.current_player == 1
    assert game.state()["monsters"] == first


def test_headshot_takes_the_monster_out_and_brings_the_next() -> None:
    game = hunt()
    target = active(game)
    game.throw(Dart(1, 1), (target["x"], target["y"]))  # the field does not matter
    state = game.state()
    assert state["monsters"][0]["status"] == "dead"
    assert state["monsters"][1]["status"] == "active"
    assert state["scores"] == [int(round(target["value"] * 1.5 / 5) * 5)]
    assert state["last_effect"]["headshot"] is True
    assert state["last_effect"]["killed"] is True
    assert state["kills"] == [1]


def test_a_graze_costs_one_life_only() -> None:
    game = hunt(seed=5)
    target = active(game)
    assert target["max_hp"] > 1
    game.throw(Dart(1, 1), graze(target))
    after = game.state()["monsters"][target["id"]]
    assert after["status"] == "active"
    assert after["hp"] == target["hp"] - 1
    assert game.state()["scores"] == [0]
    assert game.state()["last_effect"]["hit"] is True
    # enough grazes finish it off for its plain value
    for _ in range(after["hp"]):
        game.throw(Dart(1, 1), graze(game.state()["monsters"][target["id"]]))
    assert game.state()["monsters"][target["id"]]["status"] == "dead"
    assert game.state()["scores"] == [target["value"]]


def test_a_miss_makes_the_monster_grow_and_cheaper() -> None:
    game = hunt()
    before = active(game)
    game.throw(Dart.miss(), OFF)
    after = game.state()["monsters"][before["id"]]
    assert after["radius"] > before["radius"]
    assert after["value"] < before["value"]
    assert game.state()["last_effect"]["grew"] is True


def test_walkers_move_after_every_dart() -> None:
    for seed in range(1, 200):
        game = hunt(seed=seed)
        before = active(game)
        if before["kind"] == "bat":
            break
    else:
        raise AssertionError("no seed with a bat first")
    game.throw(Dart.miss(), OFF)
    after = game.state()["monsters"][before["id"]]
    assert (after["x"], after["y"]) != (before["x"], before["y"])


def test_typed_darts_use_the_middle_of_their_field() -> None:
    game = hunt(difficulty="easy")
    game.throw(Dart(25, 2))  # typed by hand: no position
    assert game.state()["arcade_darts"][0]["position"] == (0.0, 0.0)


def test_last_round_counts_double_and_decides_the_winner() -> None:
    game = hunt(2)
    for _ in range(4):
        for _ in range(2):
            game.throw(Dart.miss(), OFF)
            game.next_turn()
    assert game.state()["double_round"] is True
    target = active(game)
    game.throw(Dart(1, 1), (target["x"], target["y"]))
    assert game.state()["scores"][0] == 2 * int(round(target["value"] * 1.5 / 5) * 5)
    game.next_turn()
    game.throw(Dart.miss(), OFF)
    game.next_turn()
    assert game.finished
    assert game.winner == 0


def test_positions_survive_a_replay_from_the_database(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dartscore.api import create_app
    from dartscore.config import Settings

    with TestClient(create_app(Settings(data_dir=tmp_path / "data"))) as client:
        created = client.post(
            "/api/games",
            json={"mode": "monster_hunt", "settings": {"seed": 11, "rounds": 5},
                  "players": [{"guest_name": "A"}]},
        ).json()  # fmt: skip
        target = created["monsters"][0]
        games = client.app.state.games  # type: ignore[attr-defined]
        games.throw(Dart(1, 1), source="auto", x_mm=target["x"], y_mm=target["y"], confidence=0.9)
        live = client.get("/api/games/active").json()["scores"]
        assert live[0] > 0
        # a restart reloads the game from the database: the position must still count
        games._active = None
        games._load_active()
        assert client.get("/api/games/active").json()["scores"] == live


# --- Fruit samurai ---------------------------------------------------------------------------


def samurai(players: int = 1, rounds: int = 5) -> FruitSamuraiGame:
    game = create_game("fruit_samurai", players, {"rounds": rounds})
    assert isinstance(game, FruitSamuraiGame)
    return game


def test_a_cut_through_the_bull_line_scores_the_piece_by_size() -> None:
    game = samurai()
    game.throw(Dart(20, 1), (0.0, 85.0))  # halfway out: a cap of the fruit
    state = game.state()
    cap = state["scores"][0]
    # the circular segment beyond half the radius is ~19.6 % of the circle
    assert 190 <= cap <= 200
    assert state["last_effect"]["result"] == "slice"
    assert 0.80 <= state["fruit_share"] <= 0.81


def test_closer_to_the_bull_cuts_a_bigger_piece() -> None:
    near, far = samurai(), samurai()
    near.throw(Dart(20, 1), (0.0, 20.0))
    far.throw(Dart(20, 1), (0.0, 120.0))
    assert near.state()["scores"][0] > 400 > far.state()["scores"][0]


def test_past_the_bull_where_nothing_is_left_cuts_only_air() -> None:
    game = samurai()
    game.throw(Dart(20, 1), (0.0, 30.0))
    game.throw(Dart(20, 1), (0.0, 60.0))  # already cut away
    state = game.state()
    assert state["turn"]["values"][1] == 0
    assert state["last_effect"]["result"] == "air"


def test_the_bullseye_cuts_away_everything_left_and_ends_the_turn() -> None:
    game = samurai()
    game.throw(Dart(20, 1), (0.0, 85.0))
    game.throw(Dart(25, 2))  # typed by hand: middle of the bullseye
    state = game.state()
    assert state["scores"][0] == 1000
    assert state["last_effect"]["result"] == "perfect"
    assert state["awaiting_next"] is True


def test_every_turn_starts_with_a_fresh_fruit_and_the_last_one_is_a_watermelon() -> None:
    game = samurai(2)
    fruits = []
    for _ in range(5):
        fruits.append(game.state()["fruit"])
        for _ in range(2):
            assert game.state()["fruit_share"] == 1.0
            game.throw(Dart(20, 1), (0.0, 85.0))
            game.next_turn()
    assert fruits == ["orange", "kiwi", "dragonfruit", "lime", "watermelon"]
    assert game.state()["fruits"] == fruits
    assert game.finished
    cap = samurai()
    cap.throw(Dart(20, 1), (0.0, 85.0))
    # four normal rounds and the double last round
    assert game.state()["scores"] == [6 * cap.state()["scores"][0]] * 2


def test_three_cuts_around_the_bull_leave_a_small_piece() -> None:
    game = samurai()
    for angle in (90, 210, 330):
        a = math.radians(angle)
        game.throw(Dart(20, 1), (10 * math.cos(a), 10 * math.sin(a)))
    assert game.state()["scores"][0] > 980


def test_the_cut_fruit_stays_until_the_darts_are_pulled() -> None:
    game = samurai(2)
    game.throw(Dart(20, 1), (0.0, 30.0))
    game.throw(Dart(25, 2))  # everything gone, the turn is over
    state = game.state()
    assert state["awaiting_next"] is True
    assert state["fruit"] == "orange"
    assert state["fruit_left"] == []
    assert len(state["arcade_darts"]) == 2
    game.next_turn()
    state = game.state()
    assert state["fruit_share"] == 1.0
    assert state["arcade_darts"] == []


def test_cuts_and_holes_stay_on_the_board_for_the_whole_round() -> None:
    game = samurai(2)
    game.throw(Dart(20, 1), (0.0, 30.0))
    game.throw(Dart(25, 2))  # no cut line, but a hole
    game.next_turn()
    game.throw(Dart(6, 1), (40.0, 0.0))
    marks = game.state()["board_marks"]
    assert len(marks["cuts"]) == 2  # Alex's cut and Jens's
    assert len(marks["holes"]) == 3
    game.next_turn()
    assert game.state()["board_marks"] == {"cuts": [], "holes": []}  # round 2: a fresh board
