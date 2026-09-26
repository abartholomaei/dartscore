"""Camera endpoints: status, snapshot, MJPEG live stream and detected devices."""

import threading
from collections.abc import AsyncIterator
from typing import Annotated

import cv2
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from dartscore.config import Settings, StreamConfig
from dartscore.vision.camera import CameraManager, CameraWorker, Frame
from dartscore.vision.devices import list_devices
from dartscore.vision.intrinsics import Undistorter

router = APIRouter(prefix="/api", tags=["cameras"])

BOUNDARY = "frame"


class CameraInfo(BaseModel):
    width: int
    height: int
    fps: float
    fourcc: str
    backend: str


class CameraStatusResponse(BaseModel):
    id: str
    source: str
    device: str
    position_deg: float
    state: str
    fps: float
    frames: int
    dropped: int
    info: CameraInfo | None
    last_error: str | None
    lens_calibrated: bool
    board_calibrated: bool


class DeviceResponse(BaseModel):
    device: str
    name: str
    by_id: list[str]
    by_path: list[str]
    formats: dict[str, list[str]]


class JpegRenderer:
    """Encodes camera frames as JPEG; the last result per camera is reused
    so multiple viewers don't cause the same work repeatedly."""

    def __init__(self, stream: StreamConfig, undistorters: dict[str, Undistorter]) -> None:
        self._stream = stream
        self._undistorters = undistorters
        self._cache: dict[str, tuple[tuple[int, int, bool], bytes]] = {}
        self._lock = threading.Lock()

    def has_lens(self, camera_id: str) -> bool:
        return camera_id in self._undistorters

    def render(self, frame: Frame, width: int, undistort: bool) -> bytes:
        undistorter = self._undistorters.get(frame.camera_id) if undistort else None
        key = (frame.seq, width, undistorter is not None)
        with self._lock:
            cached = self._cache.get(frame.camera_id)
        if cached is not None and cached[0] == key:
            return cached[1]

        image = frame.image
        if undistorter is not None:
            image = undistorter.undistort(image)
        h, w = image.shape[:2]
        if width < w:
            image = cv2.resize(image, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self._stream.jpeg_quality])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        data = buf.tobytes()
        with self._lock:
            self._cache[frame.camera_id] = (key, data)
        return data


def _manager(request: Request) -> CameraManager:
    manager: CameraManager = request.app.state.cameras
    return manager


def _renderer(request: Request) -> JpegRenderer:
    renderer: JpegRenderer = request.app.state.jpeg
    return renderer


def worker_or_404(request: Request, camera_id: str) -> CameraWorker:
    worker = _manager(request).get(camera_id)
    if worker is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")
    return worker


def _width(request: Request, width: int | None) -> int:
    settings: Settings = request.app.state.settings
    return width or settings.stream.default_width


Width = Annotated[int | None, Query(ge=160, le=1920)]


@router.get("/cameras")
def list_cameras(request: Request) -> list[CameraStatusResponse]:
    renderer = _renderer(request)
    result = []
    for worker in _manager(request).workers():
        status = worker.status()
        cfg = worker.config
        result.append(
            CameraStatusResponse(
                id=status.id,
                source=cfg.source,
                device=cfg.device,
                position_deg=cfg.position_deg,
                state=status.state.value,
                fps=status.fps,
                frames=status.frames,
                dropped=status.dropped,
                info=CameraInfo(**status.info.__dict__) if status.info else None,
                last_error=status.last_error,
                lens_calibrated=renderer.has_lens(status.id),
                board_calibrated=request.app.state.calibrations.get(status.id) is not None,
            )
        )
    return result


@router.get("/cameras/{camera_id}/snapshot.jpg", response_class=Response)
async def snapshot(
    request: Request, camera_id: str, width: Width = None, undistort: bool = False
) -> Response:
    worker = worker_or_404(request, camera_id)
    frame = worker.latest() or await run_in_threadpool(worker.wait_for_frame, 0, 3.0)
    if frame is None:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} is not delivering frames")
    data = await run_in_threadpool(
        _renderer(request).render, frame, _width(request, width), undistort
    )
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/cameras/{camera_id}/stream.mjpg")
async def stream(
    request: Request,
    camera_id: str,
    width: Width = None,
    fps: Annotated[int | None, Query(ge=1, le=30)] = None,
    undistort: bool = False,
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> StreamingResponse:
    """MJPEG stream, usable directly as <img src> in the browser. ``limit`` = number of frames."""
    worker = worker_or_404(request, camera_id)
    settings: Settings = request.app.state.settings
    max_fps = min(fps or settings.stream.max_fps, settings.stream.max_fps)
    renderer = _renderer(request)
    target_width = _width(request, width)
    min_interval = 1 / max_fps

    async def frames() -> AsyncIterator[bytes]:
        seq = 0
        sent = 0
        last_ts = 0.0
        while limit is None or sent < limit:
            if await request.is_disconnected():
                break
            frame = await run_in_threadpool(worker.wait_for_frame, seq, 1.0)
            if frame is None:
                continue
            seq = frame.seq
            # throttle to the maximum stream frame rate
            if frame.timestamp - last_ts < min_interval:
                continue
            last_ts = frame.timestamp
            data = await run_in_threadpool(renderer.render, frame, target_width, undistort)
            yield (
                (
                    f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                    f"Content-Length: {len(data)}\r\n\r\n"
                ).encode()
                + data
                + b"\r\n"
            )
            sent += 1

    return StreamingResponse(
        frames(),
        media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/devices")
async def devices() -> list[DeviceResponse]:
    found = await run_in_threadpool(list_devices)
    return [
        DeviceResponse(
            device=d.device,
            name=d.name,
            by_id=d.by_id,
            by_path=d.by_path,
            formats={fourcc: [str(m) for m in modes] for fourcc, modes in d.formats.items()},
        )
        for d in found
    ]
