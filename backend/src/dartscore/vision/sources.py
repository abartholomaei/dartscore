"""Frame sources: real cameras via OpenCV and a simulated camera for development."""

import math
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np
import structlog
from numpy.typing import NDArray

from dartscore.config import CameraConfig
from dartscore.vision import board

log = structlog.get_logger(__name__)

# image in OpenCV format (BGR, HxWx3)
Image = cv2.typing.MatLike


@dataclass(frozen=True)
class SourceInfo:
    """Actually negotiated values (may differ from the configuration)."""

    width: int
    height: int
    fps: float
    fourcc: str
    backend: str


class FrameSource(Protocol):
    def open(self) -> SourceInfo: ...

    def read(self) -> Image | None: ...

    def close(self) -> None: ...


def create_source(config: CameraConfig) -> FrameSource:
    if config.source == "synthetic":
        return SyntheticSource(config)
    return OpenCVSource(config)


def _decode_fourcc(value: float) -> str:
    code = int(value)
    return "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4)).strip("\0") or "?"


def _platform_backend() -> int:
    if sys.platform.startswith("linux"):
        return cv2.CAP_V4L2
    if sys.platform == "darwin":
        return cv2.CAP_AVFOUNDATION
    if sys.platform == "win32":
        # DirectShow switches to MJPG more reliably than MSMF
        return cv2.CAP_DSHOW
    return cv2.CAP_ANY


def apply_v4l2_controls(device: str, controls: dict[str, int]) -> None:
    if not controls:
        return
    if not sys.platform.startswith("linux"):
        log.warning("v4l2_controls_ignored", reason="Linux only", device=device)
        return
    exe = shutil.which("v4l2-ctl")
    if exe is None:
        log.warning("v4l2_controls_ignored", reason="v4l2-ctl not installed", device=device)
        return
    arg = ",".join(f"{k}={v}" for k, v in controls.items())
    result = subprocess.run(
        [exe, "-d", device, "-c", arg], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        log.warning("v4l2_controls_failed", device=device, stderr=result.stderr.strip())
    else:
        log.info("v4l2_controls_applied", device=device, controls=controls)


class OpenCVSource:
    def __init__(self, config: CameraConfig) -> None:
        self._config = config
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> SourceInfo:
        cfg = self._config
        target: int | str = int(cfg.device) if cfg.device.isdigit() else cfg.device
        backend = _platform_backend()
        cap = cv2.VideoCapture(target, backend)
        if not cap.isOpened():
            cap.release()
            raise OSError(f"Cannot open camera {cfg.id} ({cfg.device})")

        # order matters: format first, then resolution and fps
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*cfg.fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        cap.set(cv2.CAP_PROP_FPS, cfg.fps)
        # Deliberately don't set the buffer size to 1: the driver then drops every other frame
        # while the previous one is decoded (measured: 15 instead of 30 fps). The reader thread
        # fetches continuously anyway, so nothing piles up in the buffer.
        if isinstance(target, str):
            apply_v4l2_controls(target, cfg.v4l2_controls)

        self._cap = cap
        info = SourceInfo(
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            fps=cap.get(cv2.CAP_PROP_FPS),
            fourcc=_decode_fourcc(cap.get(cv2.CAP_PROP_FOURCC)),
            backend=cap.getBackendName(),
        )
        if (info.width, info.height) != (cfg.width, cfg.height) or info.fourcc != cfg.fourcc:
            log.warning(
                "camera_settings_differ",
                camera=cfg.id,
                requested=f"{cfg.width}x{cfg.height} {cfg.fourcc}",
                actual=f"{info.width}x{info.height} {info.fourcc}",
            )
        return info

    def read(self) -> Image | None:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class SyntheticSource:
    """Simulated camera: the board from a side perspective, plus a moving marker.

    The perspective depends on ``position_deg`` so the three images differ.
    """

    def __init__(self, config: CameraConfig) -> None:
        self._config = config
        self._base: Image | None = None
        self._next_frame_at = 0.0
        self._started_at = 0.0

    def open(self) -> SourceInfo:
        cfg = self._config
        top_down = board.render_board(900)
        self._base = cv2.warpPerspective(
            top_down, self._view_homography(900), (cfg.width, cfg.height), borderValue=(40, 40, 40)
        )
        self._started_at = self._next_frame_at = time.monotonic()
        return SourceInfo(
            width=cfg.width, height=cfg.height, fps=cfg.fps, fourcc="SYNT", backend="synthetic"
        )

    def _view_homography(self, size: int) -> NDArray[np.float64]:
        """Map the top-down view to a squashed, rotated view (shallow, from the side)."""
        cfg = self._config
        w, h = cfg.width, cfg.height
        s = size
        src = np.array([[0, 0], [s, 0], [s, s], [0, s]], dtype=np.float32)
        # squash in depth + slight keystone distortion
        cx, cy = w / 2, h / 2
        half_w = min(w, h * 1.6) * 0.45
        half_h = half_w * 0.45
        dst = np.array(
            [
                [cx - half_w * 0.8, cy - half_h],
                [cx + half_w * 0.8, cy - half_h],
                [cx + half_w, cy + half_h],
                [cx - half_w, cy + half_h],
            ],
            dtype=np.float32,
        )
        # rotate the board according to the mounting position
        angle = cfg.position_deg
        rot = cv2.getRotationMatrix2D((s / 2, s / 2), angle, 1.0)
        rot3 = np.vstack([rot, [0, 0, 1]])
        persp = cv2.getPerspectiveTransform(src, dst)
        return np.asarray(persp @ rot3, dtype=np.float64)

    def read(self) -> Image | None:
        if self._base is None:
            return None
        # keep the frame rate like a real camera
        now = time.monotonic()
        if now < self._next_frame_at:
            time.sleep(self._next_frame_at - now)
        self._next_frame_at = max(self._next_frame_at + 1 / self._config.fps, time.monotonic())

        frame = self._base.copy()
        t = time.monotonic() - self._started_at
        h, w = frame.shape[:2]
        x = int(w / 2 + math.cos(t) * w * 0.3)
        y = int(h / 2 + math.sin(t * 1.3) * h * 0.2)
        cv2.circle(frame, (x, y), 8, (0, 220, 255), -1, cv2.LINE_AA)
        label = f"{self._config.id}  sim  {t:6.1f}s"
        cv2.putText(frame, label, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        return frame

    def close(self) -> None:
        self._base = None
