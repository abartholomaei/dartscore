from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dartscore.api import create_app
from dartscore.config import Settings
from dartscore.game import create_game
from dartscore.services.training_plans import PLANS


@pytest.mark.parametrize("plan", sorted(PLANS))
def test_every_drill_is_a_valid_game(plan: str) -> None:
    for session in PLANS[plan]:
        for drill in session:
            create_game(drill["mode"], 1, dict(drill["settings"]))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(data_dir=tmp_path / "data"))) as c:
        yield c


def test_plan_flow_records_results_and_opens_the_next_session(client: TestClient) -> None:
    pid = client.post("/api/players", json={"name": "A"}).json()["id"]
    assert client.get(f"/api/players/{pid}/training-plan").json() is None
    plan = client.put(f"/api/players/{pid}/training-plan", json={"plan": "allround"}).json()
    assert plan["current_session"] == 0
    assert len(plan["sessions"][0]) == 2
    # a later session is locked
    locked = client.post(f"/api/players/{pid}/training-plan/sessions/1/drills/0/start")
    assert locked.status_code == 422

    # drill 1 of session 1: Around the Clock (singles, with bull), goal 21 = finished
    state = client.post(f"/api/players/{pid}/training-plan/sessions/0/drills/0/start").json()
    assert state["mode"] == "around_the_clock"
    for n in [*range(1, 21), 25]:
        dart = "25" if n == 25 else f"S{n}"
        assert client.post("/api/games/active/throws", json={"dart": dart}).status_code == 200
        if not client.get("/api/games/active").json()["finished"] and n % 3 == 0:
            client.post("/api/games/active/next")
    plan = client.get(f"/api/players/{pid}/training-plan").json()
    first = plan["sessions"][0][0]
    assert first["played"] == 1
    assert first["best"] == 21
    assert first["achieved"] is True
    assert plan["current_session"] == 0  # the second drill is still open

    # drill 2: Shanghai (7 rounds), goal 60 - a poor score is recorded as missed
    client.post(f"/api/players/{pid}/training-plan/sessions/0/drills/1/start", params={})
    for _ in range(7):
        client.post("/api/games/active/next")
    plan = client.get(f"/api/players/{pid}/training-plan").json()
    assert plan["sessions"][0][1]["achieved"] is False
    assert plan["current_session"] == 1  # played, even without reaching the goal
