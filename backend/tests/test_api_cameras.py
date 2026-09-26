from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from dartscore.api import create_app
from dartscore.config import CameraConfig, Settings
from dartscore.vision import board


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


def _clicks(position_deg: float) -> dict[str, list[float]]:
    from dartscore.vision.sources import SyntheticSource

    source = SyntheticSource(
        CameraConfig(id="x", source="synthetic", width=640, height=360, position_deg=position_deg)
    )
    h = source.board_homography()
    result = {}
    for p in board.CALIBRATION_POINTS[:5]:
        v = h @ [p.x_mm, p.y_mm, 1]
        result[p.id] = [v[0] / v[2], v[1] / v[2]]
    return result


def test_calibration_roundtrip(client: TestClient) -> None:
    assert client.get("/api/calibration/points").json()["required"] == 4
    assert client.get("/api/cameras/cam2/calibration").status_code == 404

    clicks = _clicks(120)
    preview = client.post("/api/cameras/cam2/calibration/preview", json={"points": clicks})
    assert preview.status_code == 200
    assert preview.json()["rms_px"] < 0.5
    assert len(preview.json()["overlay"]["rings"]) == 6

    saved = client.put("/api/cameras/cam2/calibration", json={"points": clicks})
    assert saved.status_code == 200
    body = saved.json()
    assert body["image_size"] == [640, 360]
    assert body["undistorted"] is False
    assert body["drift_warning"] is False

    bull = clicks["bull"]
    score = client.post("/api/cameras/cam2/calibration/score", json={"x": bull[0], "y": bull[1]})
    assert score.json()["label"] == "BULL"

    cameras = {c["id"]: c for c in client.get("/api/cameras").json()}
    assert cameras["cam2"]["board_calibrated"] is True
    assert cameras["cam1"]["board_calibrated"] is False

    assert client.delete("/api/cameras/cam2/calibration").status_code == 204
    assert client.get("/api/cameras/cam2/calibration").status_code == 404


def test_calibration_rejects_bad_points(client: TestClient) -> None:
    response = client.post(
        "/api/cameras/cam1/calibration/preview", json={"points": {"20/1": [1, 2]}}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "too_few_points"
