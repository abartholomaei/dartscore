from collections.abc import Iterator
from datetime import UTC, datetime

import numpy as np
import pytest
from fastapi.testclient import TestClient

from dartscore.api import create_app
from dartscore.config import CameraConfig, Settings
from dartscore.vision.calibration import BoardCalibration, change_lens, fit_homography
from dartscore.vision.intrinsics import LensCalibration, Undistorter
from tests.test_calibration import synthetic_clicks
from tests.test_intrinsics import chessboard_texture, render_view

LENS = LensCalibration(
    camera_matrix=np.array([[700.0, 0, 640], [0, 700.0, 360], [0, 0, 1]]),
    dist_coeffs=np.array([-0.28, 0.08, 0.0, 0.0, -0.01]),
    image_size=(1280, 720),
    rms_error=0.3,
    created_at=datetime.now(UTC).isoformat(timespec="seconds"),
)


def test_distort_inverts_undistort() -> None:
    undistorter = Undistorter(LENS)
    points = np.array([[100.0, 80.0], [640.0, 360.0], [1200.0, 650.0], [300.0, 500.0]])
    there = undistorter.undistort_points(points, (1280, 720))
    back = undistorter.distort_points(there, (1280, 720))
    assert np.abs(back - points).max() < 0.05


def test_change_lens_round_trip_keeps_the_clicks() -> None:
    _, clicks = synthetic_clicks()
    fit = fit_homography(clicks)
    raw = BoardCalibration("cam", clicks, fit.homography, (1280, 720), False, None, fit.rms_px)
    lens = Undistorter(LENS)
    undistorted = change_lens(raw, None, lens)
    assert undistorted.undistorted
    assert undistorted.lens_created_at == LENS.created_at
    assert undistorted.points != raw.points
    back = change_lens(undistorted, lens, None)
    for pid, (x, y) in clicks.items():
        assert abs(back.points[pid][0] - x) < 0.1
        assert abs(back.points[pid][1] - y) < 0.1


@pytest.fixture
def client(synthetic_cameras: list[CameraConfig], tmp_path: object) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(cameras=synthetic_cameras, data_dir=tmp_path))) as c:
        yield c


def test_lens_flow_converts_the_board_calibration(client: TestClient) -> None:
    status = client.get("/api/cameras/cam1/lens").json()
    assert status["calibrated"] is False
    assert status["captures"] == 0
    capture = client.post("/api/cameras/cam1/lens/capture").json()
    assert capture["found"] is False  # no chessboard in the synthetic image
    assert client.post("/api/cameras/cam1/lens/compute").status_code == 422

    _, clicks = synthetic_clicks(0)
    assert client.put("/api/cameras/cam1/calibration", json={"points": clicks}).status_code == 200

    # feed chessboard views directly (the synthetic camera cannot show a printout)
    collector = client.app.state.lens_sessions.collector("cam1")  # type: ignore[attr-defined]
    tex = chessboard_texture()
    rng = np.random.default_rng(1)
    for _ in range(12):
        rvec = rng.uniform(-0.35, 0.35, 3)
        tvec = np.array([rng.uniform(-150, 20), rng.uniform(-100, 0), rng.uniform(550, 750)])
        collector.offer(render_view(tex, rvec, tvec))
    assert client.get("/api/cameras/cam1/lens").json()["coverage"] > 0.3

    computed = client.post("/api/cameras/cam1/lens/compute")
    assert computed.status_code == 200, computed.text
    assert computed.json()["calibrated"] is True
    assert computed.json()["board_converted"] is True
    assert computed.json()["captures"] == 0
    calibration = client.get("/api/cameras/cam1/calibration").json()
    assert calibration["undistorted"] is True
    assert calibration["stale"] is False

    removed = client.delete("/api/cameras/cam1/lens").json()
    assert removed["calibrated"] is False
    calibration = client.get("/api/cameras/cam1/calibration").json()
    assert calibration["undistorted"] is False
    for pid, (x, y) in clicks.items():
        assert abs(calibration["points"][pid][0] - x) < 0.5
        assert abs(calibration["points"][pid][1] - y) < 0.5
