import math
from pathlib import Path

from dartscore.game import Dart, create_game
from dartscore.game.arcade import MelonSamuraiGame, MonsterHuntGame


def hunt(players: int = 1, **settings: object) -> MonsterHuntGame:
    game = create_game("monster_hunt", players, {"seed": 11, "rounds": 5, **settings})
    assert isinstance(game, MonsterHuntGame)
    return game


def test_same_monsters_for_every_player_of_a_round() -> None:
    game = hunt(2)
    first = game.state()["monsters"]
    game.throw(Dart.miss())
    game.next_turn()
    assert game.current_player == 1
    assert game.state()["monsters"] == first


def test_hit_by_position_scores_and_removes_the_monster() -> None:
    game = hunt()
    target = game.state()["monsters"][0]
    game.throw(Dart(1, 1), (target["x"], target["y"]))  # the field does not matter
    state = game.state()
    assert state["monsters"][0]["alive"] is False
    assert state["scores"] == [target["value"]]
    assert state["last_effect"]["killed"] == [0]


def test_a_miss_makes_the_others_grow_and_cheaper() -> None:
    game = hunt()
    before = {m["id"]: m for m in game.state()["monsters"]}
    game.throw(Dart.miss(), (300.0, 300.0))  # far off the board
    for m in game.state()["monsters"]:
        assert m["radius"] > before[m["id"]]["radius"]
        assert m["value"] < before[m["id"]]["value"]
    assert game.state()["last_effect"]["grew"] is True


def test_typed_darts_use_the_middle_of_their_field() -> None:
    game = hunt(difficulty="easy")
    game.throw(Dart(25, 2))  # typed by hand: no position
    assert game.state()["arcade_darts"][0]["position"] == (0.0, 0.0)


def test_last_round_counts_double_and_decides_the_winner() -> None:
    game = hunt(2)
    for _ in range(4):
        for _ in range(2):
            game.throw(Dart.miss(), (300.0, 300.0))
            game.next_turn()
    assert game.state()["double_round"] is True
    target = game.state()["monsters"][0]
    game.throw(Dart(1, 1), (target["x"], target["y"]))
    assert game.state()["scores"][0] == 2 * target["value"]
    game.next_turn()
    game.throw(Dart.miss(), (300.0, 300.0))
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
        # a restart reloads the game from the database: the position must still count
        games._active = None
        games._load_active()
        assert client.get("/api/games/active").json()["scores"] == live == [target["value"]]


# --- Melon samurai ---------------------------------------------------------------------------


def samurai(players: int = 1, rounds: int = 5) -> MelonSamuraiGame:
    game = create_game("melon_samurai", players, {"rounds": rounds})
    assert isinstance(game, MelonSamuraiGame)
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


def test_caught_monsters_stay_visible_until_the_darts_are_pulled() -> None:
    game = hunt(2)
    target = game.state()["monsters"][0]
    game.throw(Dart(1, 1), (target["x"], target["y"]))
    game.throw(Dart.miss(), (300.0, 300.0))
    game.throw(Dart.miss(), (300.0, 300.0))
    state = game.state()
    assert state["awaiting_next"] is True
    assert state["monsters"][0]["alive"] is False
    assert len(state["arcade_darts"]) == 3
