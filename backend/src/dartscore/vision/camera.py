"""Camera threads: each camera reads in its own thread and holds the latest frame.

One thread per camera so three USB cameras are read in parallel at full frame rate
and a hung camera doesn't block the others.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import structlog

from dartscore.config import CameraConfig
from dartscore.vision.sources import FrameSource, Image, SourceInfo, create_source

log = structlog.get_logger(__name__)

# consecutive read failures before reconnecting
MAX_CONSECUTIVE_FAILURES = 10
RECONNECT_DELAY_MIN = 1.0
RECONNECT_DELAY_MAX = 10.0


class CameraState(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    RECONNECTING = "reconnecting"
    STOPPED = "stopped"


@dataclass(frozen=True)
class Frame:
    camera_id: str
    image: Image
    # time.monotonic() on receipt, for matching frames across the three cameras later
    timestamp: float
    seq: int


@dataclass(frozen=True)
class CameraStatus:
    id: str
    state: CameraState
    fps: float
    frames: int
    dropped: int
    info: SourceInfo | None
    last_error: str | None


class CameraWorker:
    def __init__(
        self,
        config: CameraConfig,
        source_factory: Callable[[CameraConfig], FrameSource] = create_source,
    ) -> None:
        self.config = config
        self._source_factory = source_factory
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._new_frame = threading.Condition()
        self._latest: Frame | None = None
        self._state = CameraState.STOPPED
        self._info: SourceInfo | None = None
        self._last_error: str | None = None
        self._fps = 0.0
        self._frames = 0
        self._dropped = 0

    @property
    def id(self) -> str:
        return self.config.id

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._state = CameraState.STARTING
        self._thread = threading.Thread(target=self._run, name=f"camera-{self.id}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        with self._new_frame:
            self._new_frame.notify_all()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None
        self._state = CameraState.STOPPED

    def latest(self) -> Frame | None:
        return self._latest

    def wait_for_frame(self, after_seq: int, timeout: float = 1.0) -> Frame | None:
        """Wait for a frame with seq > after_seq; None on timeout or stop."""
        with self._new_frame:
            self._new_frame.wait_for(
                lambda: (
                    self._stop.is_set()
                    or (self._latest is not None and self._latest.seq > after_seq)
                ),
                timeout,
            )
            frame = self._latest
        return frame if frame is not None and frame.seq > after_seq else None

    def status(self) -> CameraStatus:
        return CameraStatus(
            id=self.id,
            state=self._state,
            fps=round(self._fps, 1),
            frames=self._frames,
            dropped=self._dropped,
            info=self._info,
            last_error=self._last_error,
        )

    def _run(self) -> None:
        delay = RECONNECT_DELAY_MIN
        while not self._stop.is_set():
            source = self._source_factory(self.config)
            try:
                self._info = source.open()
                log.info("camera_opened", camera=self.id, **self._info.__dict__)
                self._state = CameraState.RUNNING
                self._last_error = None
                delay = RECONNECT_DELAY_MIN
                self._read_loop(source)
            except Exception as exc:
                self._last_error = str(exc)
                log.warning("camera_error", camera=self.id, error=str(exc))
            finally:
                source.close()

            if self._stop.is_set():
                break
            self._state = CameraState.RECONNECTING
            self._fps = 0.0
            self._stop.wait(delay)
            delay = min(delay * 2, RECONNECT_DELAY_MAX)

    def _read_loop(self, source: FrameSource) -> None:
        failures = 0
        last_ts: float | None = None
        expected_interval = 1 / self._info.fps if self._info and self._info.fps > 0 else None
        while not self._stop.is_set():
            image = source.read()
            if image is None:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    raise OSError(f"{failures} consecutive read failures")
                continue
            failures = 0
            now = time.monotonic()
            if last_ts is not None:
                interval = now - last_ts
                if interval > 0:
                    # moving average, reacts to changes within ~1 s
                    self._fps = (
                        0.9 * self._fps + 0.1 * (1 / interval) if self._fps else 1 / interval
                    )
                # gap > 1.5 frame intervals = dropped frame (e.g. USB bandwidth)
                if expected_interval and interval > 1.5 * expected_interval:
                    self._dropped += round(interval / expected_interval) - 1
            last_ts = now
            self._frames += 1
            frame = Frame(camera_id=self.id, image=image, timestamp=now, seq=self._frames)
            with self._new_frame:
                self._latest = frame
                self._new_frame.notify_all()


class CameraManager:
    def __init__(
        self,
        configs: list[CameraConfig],
        source_factory: Callable[[CameraConfig], FrameSource] = create_source,
    ) -> None:
        self._workers = {c.id: CameraWorker(c, source_factory) for c in configs}

    def start(self) -> None:
        for worker in self._workers.values():
            worker.start()

    def stop(self) -> None:
        for worker in self._workers.values():
            worker.stop()

    def get(self, camera_id: str) -> CameraWorker | None:
        return self._workers.get(camera_id)

    def workers(self) -> list[CameraWorker]:
        return list(self._workers.values())
