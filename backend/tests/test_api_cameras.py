from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from dartscore.api import create_app
from dartscore.config import CameraConfig, Settings


@pytest.fixture
def client(synthetic_cameras: list[CameraConfig], tmp_path: object) -> Iterator[TestClient]:
    settings = Settings(cameras=synthetic_cameras, data_dir=tmp_path)
    # the context manager starts the camera threads (lifespan)
    with TestClient(create_app(settings)) as c:
        yield c


def test_list_cameras(client: TestClient) -> None:
    response = client.get("/api/cameras")
    assert response.status_code == 200
    cameras = response.json()
    assert [c["id"] for c in cameras] == ["cam1", "cam2", "cam3"]
    assert cameras[1]["position_deg"] == 120
    assert cameras[0]["source"] == "synthetic"
    assert cameras[0]["lens_calibrated"] is False


def test_snapshot_is_jpeg_with_requested_width(client: TestClient) -> None:
    response = client.get("/api/cameras/cam1/snapshot.jpg?width=320")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


def test_stream_delivers_multipart_frames(client: TestClient) -> None:
    response = client.get("/api/cameras/cam2/stream.mjpg?limit=2")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert response.content.count(b"--frame\r\n") == 2


def test_unknown_camera_is_404(client: TestClient) -> None:
    assert client.get("/api/cameras/nope/snapshot.jpg").status_code == 404
