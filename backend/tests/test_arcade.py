from pathlib import Path

from dartscore.game import Dart, create_game
from dartscore.game.arcade import MonsterHuntGame


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
