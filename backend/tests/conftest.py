from pathlib import Path

import pytest

from dartscore.config import CameraConfig


@pytest.fixture(autouse=True)
def _isolated_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # relative defaults (data dir, database) must never touch the repository
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def synthetic_cameras() -> list[CameraConfig]:
    return [
        CameraConfig(
            id=f"cam{i + 1}",
            source="synthetic",
            width=640,
            height=360,
            fps=30,
            position_deg=i * 120,
        )
        for i in range(3)
    ]
