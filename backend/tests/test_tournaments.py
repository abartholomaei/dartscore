from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dartscore.api import create_app
from dartscore.config import Settings
from dartscore.services.tournaments import knockout_matches, round_robin_matches


def test_knockout_bracket_with_byes() -> None:
    matches = knockout_matches(5)  # bracket of 8: three byes
    first = [m for m in matches if m["round"] == 1]
    assert len(first) == 4
    assert sum(m["bye"] for m in first) == 3
    assert len([m for m in matches if m["round"] == 3]) == 1  # the final
    # byes advance their player right away
    second = [m for m in matches if m["round"] == 2]
    assert sum(x is not None for m in second for x in (m["a"], m["b"])) == 3
    # seed 1 and seed 2 can only meet in the final
    top_half = {e for m in first[:2] for e in (m["a"], m["b"])}
    assert 0 in top_half
    assert 1 not in top_half


def test_round_robin_everybody_meets_everybody() -> None:
    matches = round_robin_matches(5)
    pairs = {frozenset((m["a"], m["b"])) for m in matches}
    assert len(matches) == 10
    assert len(pairs) == 10


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(data_dir=tmp_path / "data"))) as c:
        c.app.state.bots.stop()  # type: ignore[attr-defined]
        yield c


def win_game(client: TestClient) -> None:
    # 101 checked out by the first player
    for dart in ("T20", "S1", "D20"):
        assert client.post("/api/games/active/throws", json={"dart": dart}).status_code == 200


def test_knockout_tournament_flow(client: TestClient) -> None:
    created = client.post(
        "/api/tournaments",
        json={"name": "Sunday Cup", "format": "knockout", "mode": "x01",
              "settings": {"start_score": 101},
              "entries": [{"guest_name": n} for n in ("A", "B", "C")]},
    )  # fmt: skip
    assert created.status_code == 201, created.text
    t: dict[str, Any] = created.json()
    playable = [
        m for m in t["matches"] if m["winner"] is None and m["a"] is not None and m["b"] is not None
    ]
    assert len(playable) == 1  # one semi-final, the other has a bye
    state = client.post(f"/api/tournaments/{t['id']}/matches/{playable[0]['id']}/start").json()
    names = [t["players"][playable[0][side]]["name"] for side in ("a", "b")]
    assert [p["name"] for p in state["players"]] == names
    win_game(client)
    t = client.get(f"/api/tournaments/{t['id']}").json()
    final = max(t["matches"], key=lambda m: m["round"])
    assert final["a"] is not None
    assert final["b"] is not None
    client.post(f"/api/tournaments/{t['id']}/matches/{final['id']}/start")
    win_game(client)
    t = client.get(f"/api/tournaments/{t['id']}").json()
    assert t["status"] == "finished"
    assert t["champion"] == final["a"]
    assert client.get(f"/api/tournaments/by-game/{state['id']}").json()["id"] == t["id"]


def test_round_robin_standings(client: TestClient) -> None:
    t = client.post(
        "/api/tournaments",
        json={
            "name": "League",
            "format": "round_robin",
            "mode": "x01",
            "settings": {"start_score": 101},
            "entries": [{"guest_name": "A"}, {"guest_name": "B"}],
        },
    ).json()
    assert len(t["matches"]) == 1
    client.post(f"/api/tournaments/{t['id']}/matches/0/start")
    win_game(client)
    t = client.get(f"/api/tournaments/{t['id']}").json()
    assert t["standings"][0] == {"entry": t["matches"][0]["a"], "played": 1, "won": 1,
                                 "legs_for": 1, "legs_against": 0}  # fmt: skip
    assert t["status"] == "finished"
