import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dartscore.api import create_app
from dartscore.config import CameraConfig, Settings
from dartscore.training.dataset import export_dataset
from dartscore.vision import board
from dartscore.vision.sources import SIMULATED_BOARD, SyntheticSource


def wait_for(check: Callable[[], Any], timeout: float = 5.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("timed out")


def clicks(cam: CameraConfig) -> dict[str, list[float]]:
    h = SyntheticSource(cam).board_homography()
    result = {}
    for p in board.CALIBRATION_POINTS:
        v = h @ [p.x_mm, p.y_mm, 1]
        result[p.id] = [v[0] / v[2], v[1] / v[2]]
    return result


@pytest.fixture
def client(synthetic_cameras: list[CameraConfig], tmp_path: Path) -> Iterator[TestClient]:
    SIMULATED_BOARD.clear()
    settings = Settings(cameras=synthetic_cameras, data_dir=tmp_path / "data")
    with TestClient(create_app(settings)) as c:
        for cam in synthetic_cameras:
            assert (
                c.put(
                    f"/api/cameras/{cam.id}/calibration", json={"points": clicks(cam)}
                ).status_code
                == 200
            )
        wait_for(lambda: c.get("/api/detection").json()["available"])
        yield c
    SIMULATED_BOARD.clear()


def test_detected_darts_and_takeout_drive_the_game(client: TestClient, tmp_path: Path) -> None:
    status = client.get("/api/detection").json()
    assert status["enabled"] is True
    assert sorted(status["cameras"]) == ["cam1", "cam2", "cam3"]

    client.post(
        "/api/games", json={"mode": "x01", "players": [{"guest_name": "A"}, {"guest_name": "B"}]}
    )
    time.sleep(0.5)  # references settle

    client.post("/api/simulator", json={"action": "dart", "x_mm": 0, "y_mm": 103})

    def active() -> dict[str, Any]:
        state: dict[str, Any] = client.get("/api/games/active").json()
        return state

    state = wait_for(lambda: active() if active()["turn"] else None)
    assert state["turn"]["darts"] == ["T20"]
    assert state["turn_sources"] == ["auto"]
    assert state["remaining"][0] == 441

    for x, y in [(0, 60), (60, 0)]:
        before = client.get("/api/games/active").json()["event_count"]
        client.post("/api/simulator", json={"action": "dart", "x_mm": x, "y_mm": y})

        def counted(previous: int = before) -> bool:
            return bool(active()["event_count"] > previous)

        wait_for(counted)
    state = client.get("/api/games/active").json()
    assert state["awaiting_next"] is True
    assert len(state["turn"]["darts"]) == 3

    # pull the darts: hand in view, board cleared, hand gone
    client.post("/api/simulator", json={"action": "hand", "on": True})
    time.sleep(0.6)
    client.post("/api/simulator", json={"action": "clear"})
    time.sleep(0.3)
    client.post("/api/simulator", json={"action": "hand", "on": False})
    state = wait_for(lambda: active() if active()["current_player"] == 1 else None)
    assert state["awaiting_next"] is False

    # every detection was recorded with images and metadata
    recordings = sorted((tmp_path / "data" / "recordings").rglob("meta.json"))
    assert len(recordings) == 3
    assert (recordings[0].parent / "cam1_after.jpg").is_file()

    # recordings become a labeled dataset: after the third dart, three tips per image
    stats = export_dataset(tmp_path / "data" / "recordings", tmp_path / "ds")
    assert stats.images == 9
    labels = sorted((tmp_path / "ds" / "labels").rglob("*.txt"))
    last = [line for line in labels[-1].read_text().splitlines() if line.startswith("0 ")]
    assert len(last) == 3
    assert (tmp_path / "ds" / "data.yaml").is_file()


def test_detection_can_be_switched_off(client: TestClient) -> None:
    assert client.put("/api/detection", json={"enabled": False}).json()["enabled"] is False
    client.post("/api/games", json={"mode": "x01", "players": [{"guest_name": "A"}]})
    client.post("/api/simulator", json={"action": "dart", "x_mm": 0, "y_mm": 103})
    time.sleep(1.0)
    assert client.get("/api/games/active").json()["turn"] is None


def test_simulator_requires_synthetic_cameras(tmp_path: Path) -> None:
    with TestClient(create_app(Settings(data_dir=tmp_path / "d"))) as c:
        assert c.post("/api/simulator", json={"action": "clear"}).status_code == 404
