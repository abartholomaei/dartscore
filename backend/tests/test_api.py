from fastapi.testclient import TestClient

from dartscore import __version__
from dartscore.api import create_app
from dartscore.config import CameraConfig, Settings


def test_health() -> None:
    settings = Settings(cameras=[CameraConfig(id="cam1", device="0")])
    client = TestClient(create_app(settings))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "cameras_configured": 1}
