import time

import numpy as np
import pytest

from dartscore.config import CameraConfig
from dartscore.vision import board
from dartscore.vision.camera import CameraManager, CameraState, CameraWorker
from dartscore.vision.sources import Image, SourceInfo, SyntheticSource


def wait_until(condition: object, timeout: float = 3.0) -> None:
    assert callable(condition)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError("Bedingung nicht erfüllt")


def test_board_geometry() -> None:
    assert len(board.SEGMENTS) == 20
    assert sorted(board.SEGMENTS) == list(range(1, 21))
    img = board.render_board(400)
    assert img.shape == (400, 400, 3)
    # Bullseye in der Mitte ist rot (BGR)
    _, g, r = img[200, 200]
    assert r > 150
    assert g < 100


def test_synthetic_source_delivers_configured_size(synthetic_cameras: list[CameraConfig]) -> None:
    source = SyntheticSource(synthetic_cameras[0])
    info = source.open()
    frame = source.read()
    source.close()
    assert (info.width, info.height) == (640, 360)
    assert frame is not None
    assert frame.shape == (360, 640, 3)


def test_worker_produces_frames(synthetic_cameras: list[CameraConfig]) -> None:
    worker = CameraWorker(synthetic_cameras[0])
    worker.start()
    try:
        first = worker.wait_for_frame(0, 3.0)
        assert first is not None
        second = worker.wait_for_frame(first.seq, 3.0)
        assert second is not None
        assert second.seq > first.seq
        assert second.timestamp >= first.timestamp
        wait_until(lambda: worker.status().fps > 10)
        assert worker.status().state is CameraState.RUNNING
    finally:
        worker.stop()
    assert worker.status().state is CameraState.STOPPED


class FlakySource:
    """Liefert ein paar Bilder und fällt dann aus – wie ein abgezogenes USB-Kabel."""

    opened = 0

    def __init__(self, config: CameraConfig) -> None:
        self.reads = 0

    def open(self) -> SourceInfo:
        FlakySource.opened += 1
        return SourceInfo(width=8, height=8, fps=100, fourcc="TEST", backend="test")

    def read(self) -> Image | None:
        self.reads += 1
        time.sleep(0.005)
        return np.zeros((8, 8, 3), np.uint8) if self.reads <= 3 else None

    def close(self) -> None:
        pass


def test_worker_reconnects_after_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dartscore.vision.camera.RECONNECT_DELAY_MIN", 0.05)
    FlakySource.opened = 0
    worker = CameraWorker(CameraConfig(id="flaky", source="synthetic"), FlakySource)
    worker.start()
    try:
        # nach 10 Lesefehlern schließt der Worker die Quelle und öffnet sie neu
        wait_until(lambda: FlakySource.opened >= 2)
    finally:
        worker.stop()


def test_manager_runs_all_cameras(synthetic_cameras: list[CameraConfig]) -> None:
    manager = CameraManager(synthetic_cameras)
    manager.start()
    try:
        for worker in manager.workers():
            assert worker.wait_for_frame(0, 3.0) is not None
        assert manager.get("cam2") is not None
        assert manager.get("nope") is None
    finally:
        manager.stop()
