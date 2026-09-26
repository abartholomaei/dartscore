from pathlib import Path

from fastapi.testclient import TestClient

from dartscore import __version__
from dartscore.api import create_app
from dartscore.config import CameraConfig, Settings


def test_health() -> None:
    settings = Settings(cameras=[CameraConfig(id="cam1", source="synthetic")])
    client = TestClient(create_app(settings))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "cameras_configured": 1}


def test_serves_frontend_with_spa_fallback(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>dartscore</html>")
    client = TestClient(create_app(Settings(frontend_dir=tmp_path)))

    assert "dartscore" in client.get("/").text
    # client route without a file → index.html
    assert "dartscore" in client.get("/cameras").text
    # API paths are not redirected
    assert client.get("/api/unknown").status_code == 404
