"""Lens calibration in the browser: the player holds a printed chessboard in front of a camera,
the page captures images until the image area is covered, then the distortion is computed.

An existing board calibration is carried over to the new lens model automatically.
"""

import contextlib
import threading
from datetime import datetime
from typing import Any

import cv2
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from dartscore.api.calibration import CalibrationStore
from dartscore.api.cameras import worker_or_404
from dartscore.config import Settings
from dartscore.vision.calibration import CalibrationError, change_lens
from dartscore.vision.intrinsics import (
    DEFAULT_PATTERN,
    ChessboardCollector,
    LensCalibration,
    Undistorter,
    calibrate,
    lens_file,
    save_lens,
)
from dartscore.vision.realign import RealignError
from dartscore.vision.sources import Image

router = APIRouter(prefix="/api", tags=["lens"])

# captures needed for a stable result (with good coverage of the image edges)
RECOMMENDED_CAPTURES = 15
MIN_CAPTURES = 8
# the image is divided into GRID x GRID cells; coverage = share of cells with chessboard corners
GRID = 3


class LensSessions:
    """Captures collected so far, per camera (in memory until computed)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.collectors: dict[str, ChessboardCollector] = {}

    def collector(self, camera_id: str) -> ChessboardCollector:
        with self.lock:
            return self.collectors.setdefault(camera_id, ChessboardCollector(DEFAULT_PATTERN))

    def reset(self, camera_id: str) -> None:
        with self.lock:
            self.collectors.pop(camera_id, None)


class LensStatus(BaseModel):
    calibrated: bool
    rms_error: float | None
    created_at: str | None
    captures: int
    recommended: int
    minimum: int
    coverage: float
    pattern: tuple[int, int]


class CaptureResponse(LensStatus):
    found: bool
    accepted: bool
    # detected inner corners (image px) and the image size, for drawing an overlay
    corners: list[tuple[float, float]]
    image_size: tuple[int, int] | None


class ComputeResponse(LensStatus):
    board_converted: bool


def _sessions(request: Request) -> LensSessions:
    sessions: LensSessions = request.app.state.lens_sessions
    return sessions


def _undistorters(request: Request) -> dict[str, Undistorter]:
    undistorters: dict[str, Undistorter] = request.app.state.undistorters
    return undistorters


def _coverage(collector: ChessboardCollector) -> float:
    if collector.image_size is None or not collector.detections:
        return 0.0
    w, h = collector.image_size
    cells: set[tuple[int, int]] = set()
    for corners in collector.detections:
        for x, y in corners.reshape(-1, 2):
            cells.add((min(int(x / w * GRID), GRID - 1), min(int(y / h * GRID), GRID - 1)))
    return round(len(cells) / GRID**2, 2)


def _status(request: Request, camera_id: str) -> dict[str, Any]:
    undistorter = _undistorters(request).get(camera_id)
    lens = undistorter.calibration if undistorter else None
    collector = _sessions(request).collector(camera_id)
    return {
        "calibrated": lens is not None,
        "rms_error": round(lens.rms_error, 3) if lens else None,
        "created_at": lens.created_at if lens else None,
        "captures": len(collector.detections),
        "recommended": RECOMMENDED_CAPTURES,
        "minimum": MIN_CAPTURES,
        "coverage": _coverage(collector),
        "pattern": collector.pattern,
    }


def _raw_frame(request: Request, camera_id: str) -> Image:
    worker = worker_or_404(request, camera_id)
    frame = worker.latest() or worker.wait_for_frame(0, 3.0)
    if frame is None:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} is not delivering images")
    return frame.image


@router.get("/cameras/{camera_id}/lens")
def lens_status(request: Request, camera_id: str) -> LensStatus:
    worker_or_404(request, camera_id)
    return LensStatus(**_status(request, camera_id))


@router.post("/cameras/{camera_id}/lens/capture")
def capture(request: Request, camera_id: str) -> CaptureResponse:
    """Looks for the chessboard in the current image and keeps it if it adds a new view."""
    image = _raw_frame(request, camera_id)
    collector = _sessions(request).collector(camera_id)
    before = len(collector.detections)
    try:
        accepted = collector.offer(image)
    except ValueError as exc:  # resolution changed
        _sessions(request).reset(camera_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    corners = collector.detections[-1] if accepted else None
    found = accepted or collector.last_corners is not None
    if corners is None and collector.last_corners is not None:
        corners = collector.last_corners
    if accepted and before < len(collector.detections):
        settings: Settings = request.app.state.settings
        image_dir = lens_file(settings.calibration_dir, camera_id).parent / "lens_images"
        image_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(image_dir / f"{datetime.now():%Y%m%d-%H%M%S-%f}.png"), image)
    h, w = image.shape[:2]
    return CaptureResponse(
        **_status(request, camera_id),
        found=found,
        accepted=accepted,
        corners=[(round(float(x), 1), round(float(y), 1)) for x, y in corners.reshape(-1, 2)]
        if corners is not None
        else [],
        image_size=(w, h),
    )


@router.delete("/cameras/{camera_id}/lens/captures")
def reset_captures(request: Request, camera_id: str) -> LensStatus:
    worker_or_404(request, camera_id)
    _sessions(request).reset(camera_id)
    return LensStatus(**_status(request, camera_id))


def _install(request: Request, camera_id: str, lens: LensCalibration | None) -> bool:
    """Switches the camera to another lens model (None: raw images) and carries the board
    calibration over. Returns True if a board calibration was converted."""
    store: CalibrationStore = request.app.state.calibrations
    undistorters = _undistorters(request)
    old = undistorters.get(camera_id)
    new = Undistorter(lens) if lens is not None else None
    calibration = store.get(camera_id)
    converted = None
    reference = None
    if calibration is not None and calibration.points:
        raw = _raw_frame(request, camera_id)
        current = old.undistort(raw) if calibration.undistorted and old else raw
        # follow a camera that moved since the reference image was taken
        with contextlib.suppress(RealignError):
            calibration, _ = store.realign(camera_id, current, min_move_px=1.0)
        try:
            converted = change_lens(calibration, old, new)
            reference = new.undistort(raw) if new else raw
        except CalibrationError:
            converted = None
    if new is not None:
        undistorters[camera_id] = new
    else:
        undistorters.pop(camera_id, None)
    if converted is not None and reference is not None:
        store.save(converted, reference)  # also rebuilds the detector
    else:
        reconfigure = getattr(request.app.state, "reconfigure_detection", None)
        if reconfigure is not None:
            reconfigure()
    return converted is not None


@router.post("/cameras/{camera_id}/lens/compute")
async def compute(request: Request, camera_id: str) -> ComputeResponse:
    worker_or_404(request, camera_id)
    collector = _sessions(request).collector(camera_id)
    if len(collector.detections) < MIN_CAPTURES or collector.image_size is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "too_few_captures", "message": f"At least {MIN_CAPTURES} captures"},
        )
    settings: Settings = request.app.state.settings
    lens = await run_in_threadpool(
        calibrate, collector.detections, collector.image_size, collector.pattern
    )
    await run_in_threadpool(save_lens, lens, settings.calibration_dir, camera_id)
    converted = await run_in_threadpool(_install, request, camera_id, lens)
    _sessions(request).reset(camera_id)
    return ComputeResponse(**_status(request, camera_id), board_converted=converted)


@router.delete("/cameras/{camera_id}/lens")
async def remove_lens(request: Request, camera_id: str) -> LensStatus:
    """Back to raw images (the board calibration is converted back)."""
    worker_or_404(request, camera_id)
    settings: Settings = request.app.state.settings
    await run_in_threadpool(_install, request, camera_id, None)
    path = lens_file(settings.calibration_dir, camera_id)
    if path.is_file():
        path.rename(path.with_suffix(f".removed-{datetime.now():%Y%m%d%H%M%S}.json"))
    return LensStatus(**_status(request, camera_id))
