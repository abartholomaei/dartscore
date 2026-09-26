from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dartscore.api import create_app
from dartscore.config import Settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(data_dir=tmp_path / "data"))) as c:
        yield c


def make_players(client: TestClient, *names: str) -> list[int]:
    return [client.post("/api/players", json={"name": n}).json()["id"] for n in names]


def throw(client: TestClient, *labels: str) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for label in labels:
        if label == "NEXT":
            response = client.post("/api/games/active/next")
        else:
            response = client.post("/api/games/active/throws", json={"dart": label})
        assert response.status_code == 200, response.text
        state = response.json()
    return state


def test_player_crud(client: TestClient) -> None:
    created = client.post("/api/players", json={"name": "  Alex  "})
    assert created.status_code == 201
    alex = created.json()
    assert alex["name"] == "Alex"
    assert alex["color"].startswith("#")

    dup = client.post("/api/players", json={"name": "alex"})
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "name_taken"

    renamed = client.patch(
        f"/api/players/{alex['id']}", json={"name": "Alexander", "color": "#123456"}
    )
    assert renamed.json()["name"] == "Alexander"
    assert [p["name"] for p in client.get("/api/players").json()] == ["Alexander"]

    assert client.delete(f"/api/players/{alex['id']}").status_code == 204
    assert client.get("/api/players").json() == []
    assert client.get(f"/api/players/{alex['id']}").status_code == 404


def test_player_with_games_is_archived_not_deleted(client: TestClient) -> None:
    (pid,) = make_players(client, "Anna")
    client.post("/api/games", json={"mode": "x01", "players": [{"player_id": pid}]})
    client.post("/api/games/active/abort")

    response = client.delete(f"/api/players/{pid}")
    assert response.status_code == 200
    assert response.json()["archived"] is True
    assert client.get("/api/players").json() == []
    assert len(client.get("/api/players?include_archived=true").json()) == 1
    assert client.post(f"/api/players/{pid}/restore").json()["archived"] is False


def test_full_x01_game_with_guest(client: TestClient) -> None:
    (anna,) = make_players(client, "Anna")
    created = client.post(
        "/api/games",
        json={
            "mode": "x01",
            "settings": {"start_score": 101},
            "players": [{"player_id": anna}, {"guest_name": "Bob"}],
        },
    )
    assert created.status_code == 201
    state = created.json()
    assert [p["name"] for p in state["players"]] == ["Anna", "Bob"]
    assert state["players"][1]["guest"] is True

    state = throw(client, "T20", "S1", "MISS")
    assert state["remaining"] == [40, 101]
    assert state["awaiting_next"] is True
    assert state["checkout"] is None or state["current_player"] == 0

    state = throw(client, "NEXT", "S20", "NEXT", "D20")
    assert state["finished"] is True
    assert state["winner"] == 0
    assert state["players"][0]["stats"]["average"] == pytest.approx(101 / 4 * 3, abs=0.01)
    assert client.get("/api/games/active").json()["finished"] is True

    history = client.get("/api/games").json()
    assert history == [] or history[0]["status"] == "finished"


def test_second_game_conflicts_unless_aborting(client: TestClient) -> None:
    body = {"mode": "cricket", "players": [{"guest_name": "A"}, {"guest_name": "B"}]}
    assert client.post("/api/games", json=body).status_code == 201
    conflict = client.post("/api/games", json=body)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "game_active"
    assert client.post("/api/games", json={**body, "abort_active": True}).status_code == 201
    assert client.get("/api/games").json()[0]["status"] == "aborted"


def test_finished_game_does_not_block_and_stays_finished(client: TestClient) -> None:
    body = {"mode": "x01", "settings": {"start_score": 101}, "players": [{"guest_name": "A"}]}
    client.post("/api/games", json=body)
    throw(client, "T20", "S1", "D20")
    assert client.post("/api/games", json=body).status_code == 201
    assert client.get("/api/games").json()[0]["status"] == "finished"


def test_undo_correct_and_errors(client: TestClient) -> None:
    client.post(
        "/api/games",
        json={"mode": "x01", "settings": {"start_score": 301}, "players": [{"guest_name": "A"}]},
    )
    throw(client, "T20", "T20")
    state = client.post("/api/games/active/undo").json()
    assert state["remaining"] == [241]

    state = client.put(
        "/api/games/active/darts", json={"turn_index": -1, "dart_index": 0, "dart": "T19"}
    ).json()
    assert state["remaining"] == [244]

    bad = client.post("/api/games/active/throws", json={"dart": "T25"})
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "invalid_dart"

    client.post("/api/games/active/abort")
    missing = client.post("/api/games/active/next")
    assert missing.status_code == 404


def test_game_survives_restart(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    with TestClient(create_app(settings)) as first:
        first.post("/api/games", json={"mode": "x01", "players": [{"guest_name": "A"}]})
        throw(first, "T20", "T20")
    with TestClient(create_app(settings)) as second:
        state = second.get("/api/games/active").json()
        assert state["remaining"] == [381]
        state = throw(second, "T20")
        assert state["remaining"] == [321]


def test_stats_and_head_to_head(client: TestClient) -> None:
    a, b = make_players(client, "A", "B")
    for _ in range(2):
        client.post(
            "/api/games",
            json={
                "mode": "x01",
                "settings": {"start_score": 101},
                "players": [{"player_id": a}, {"player_id": b}],
                "abort_active": True,
            },
        )
        state = client.get("/api/games/active").json()
        starter = state["current_player"]
        # whoever starts checks out 101 in three darts
        throw(client, "T20", "S1", "D20")
        winner = state["players"][starter]["player_id"]
        assert winner in (a, b)

    stats = client.get(f"/api/stats/players/{a}").json()
    x01 = stats["modes"]["x01"]
    assert x01["games"] == 2
    assert x01["darts"] >= 3

    h2h = client.get(f"/api/stats/head-to-head?a={a}&b={b}").json()
    assert h2h["games"] == 2
    assert sum(h2h["wins"].values()) == 2

    rematch = client.post("/api/games/rematch")
    assert rematch.status_code == 201


def test_websocket_receives_updates(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json() == {"type": "game", "data": None}
        assert ws.receive_json()["type"] == "detection"
        client.post("/api/games", json={"mode": "x01", "players": [{"guest_name": "A"}]})
        message = ws.receive_json()
        assert message["type"] == "game"
        assert message["data"]["mode"] == "x01"
        client.post("/api/games/active/throws", json={"dart": "T20"})
        assert ws.receive_json()["data"]["remaining"] == [441]


def test_bounce_scores_nothing_and_is_marked(client: TestClient) -> None:
    client.post("/api/games", json={"mode": "x01", "players": [{"guest_name": "A"}]})
    throw(client, "S20", "T20")
    state = client.put(
        "/api/games/active/darts", json={"turn_index": -1, "dart_index": 1, "bounce": True}
    ).json()
    assert state["turn"]["darts"] == ["S20", "MISS"]
    assert state["remaining"] == [481]
    assert state["turn_sources"] == ["manual", "bounce"]


@pytest.mark.parametrize(
    "mode", ["around_the_clock", "shanghai", "bobs_27", "checkout_training", "doubles_training"]
)
def test_training_modes_via_api(client: TestClient, mode: str) -> None:
    created = client.post(
        "/api/games", json={"mode": mode, "players": [{"guest_name": "A"}], "abort_active": True}
    )
    assert created.status_code == 201, created.text
    state = throw(client, "D1", "MISS", "MISS")
    assert state["mode"] == mode
    assert "score" in state["players"][0]["stats"]


def test_favorite_double_drives_checkout_suggestion(client: TestClient) -> None:
    (pid,) = make_players(client, "Dora")
    updated = client.patch(
        f"/api/players/{pid}", json={"favorite_double": 16, "throwing_hand": "left"}
    ).json()
    assert updated["favorite_double"] == 16
    assert updated["throwing_hand"] == "left"
    assert client.patch(f"/api/players/{pid}", json={"favorite_double": 21}).status_code == 422

    client.post(
        "/api/games",
        json={"mode": "x01", "settings": {"start_score": 101}, "players": [{"player_id": pid}]},
    )
    # 64 left: normally T16 D8, with the favourite double a route ending on D16
    state = throw(client, "T12", "S1", "MISS", "NEXT")
    assert state["remaining"] == [64]
    assert state["checkout"][-1] == "D16"
    assert state["settings"]["preferred_doubles"] == [16]


def test_exports_and_double_rates(client: TestClient) -> None:
    (pid,) = make_players(client, "Eva")
    client.post(
        "/api/games",
        json={"mode": "x01", "settings": {"start_score": 101}, "players": [{"player_id": pid}]},
    )
    # 101 - 60 - 1 = 40: two darts at D20, the second one hits
    throw(client, "T20", "S1", "S20", "NEXT", "D10")
    rates = client.get(f"/api/stats/players/{pid}/doubles").json()
    assert rates == {"20": {"attempts": 1, "hits": 0}, "10": {"attempts": 1, "hits": 1}}

    client.post(
        "/api/games",
        json={
            "mode": "doubles_training",
            "settings": {"include_bull": False},
            "players": [{"player_id": pid}],
        },
    )
    throw(client, "D1", "S1", "MISS")
    client.post("/api/games/active/abort")
    rates = client.get(f"/api/stats/players/{pid}/doubles").json()
    assert rates["1"] == {"attempts": 3, "hits": 1}

    games = client.get("/api/export/games.csv")
    assert games.headers["content-type"].startswith("text/csv")
    assert "Eva" in games.text
    darts = client.get("/api/export/darts.csv").text.splitlines()
    assert darts[0].startswith("game_id,seq")
    assert len(darts) == 1 + 4 + 3  # header, x01 darts, doubles training darts
    full = client.get("/api/export/all.json").json()
    assert full["format"] == "dartscore-1"
    assert len(full["games"]) == 2

    assert client.get(f"/api/stats/players/{pid}?days=7").json()["modes"]["x01"]["games"] == 1


def test_achievements(client: TestClient) -> None:
    a, b = make_players(client, "A", "B")
    players = [{"player_id": a}, {"player_id": b}]
    empty = client.get(f"/api/stats/players/{a}/achievements").json()
    assert all(item["achieved_at"] is None for item in empty)

    client.post(
        "/api/games", json={"mode": "x01", "settings": {"start_score": 170}, "players": players}
    )
    throw(client, "T20", "T20", "BULL")
    client.post(
        "/api/games",
        json={
            "mode": "x01",
            "settings": {"start_score": 501},
            "players": players,
            "abort_active": True,
        },
    )
    throw(client, "T20", "T20", "T20", "NEXT", "NEXT", "T20", "T20", "T20", "NEXT", "NEXT")
    throw(client, "T20", "T19", "D12")

    got = {i["id"]: i for i in client.get(f"/api/stats/players/{a}/achievements").json()}
    unlocked = {key for key, item in got.items() if item["achieved_at"]}
    assert {"first_win", "big_fish", "ton_out", "bull_finish", "one_eighty", "nine_darter",
            "leg_12", "average_100"} <= unlocked  # fmt: skip
    assert "shanghai" not in unlocked
    assert got["big_fish"]["game_id"] != got["nine_darter"]["game_id"]
    others = client.get(f"/api/stats/players/{b}/achievements").json()
    assert {i["id"] for i in others if i["achieved_at"]} == {"first_game"}


def test_grouping_uses_detected_positions(client: TestClient) -> None:
    (a,) = make_players(client, "A")
    client.post("/api/games", json={"mode": "score_training", "settings": {"rounds": 5},
                                    "players": [{"player_id": a}]})  # fmt: skip
    games = client.app.state.games  # type: ignore[attr-defined]
    from dartscore.game import Dart

    for x in (0.0, 6.0, 3.0):
        games.throw(Dart(20, 1), source="auto", x_mm=x, y_mm=130.0, confidence=0.9)
    client.post("/api/games/active/abort")
    result = client.get(f"/api/stats/players/{a}/grouping").json()
    assert result["turns"] == 1
    assert result["best_mm"] == 2.0  # distances 3, 3, 0 from the centre


def test_pin_protects_profile(client: TestClient) -> None:
    (a,) = make_players(client, "A")
    set_pin = client.patch(f"/api/players/{a}", json={"new_pin": "1234"})
    assert set_pin.json()["has_pin"] is True
    blocked = client.patch(f"/api/players/{a}", json={"name": "B"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "pin_required"
    wrong = client.patch(f"/api/players/{a}", json={"name": "B"}, headers={"X-Player-Pin": "0000"})
    assert wrong.json()["detail"]["code"] == "wrong_pin"
    assert client.delete(f"/api/players/{a}").status_code == 403
    ok = client.patch(f"/api/players/{a}", json={"name": "B"}, headers={"X-Player-Pin": "1234"})
    assert ok.json()["name"] == "B"
    assert (
        client.patch(
            f"/api/players/{a}", json={"new_pin": "12"}, headers={"X-Player-Pin": "1234"}
        ).status_code
        == 422
    )
    cleared = client.patch(
        f"/api/players/{a}", json={"new_pin": None}, headers={"X-Player-Pin": "1234"}
    )
    assert cleared.json()["has_pin"] is False
    assert client.delete(f"/api/players/{a}").status_code == 204
