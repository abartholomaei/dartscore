"""Board calibration endpoints: point catalog, preview, save, score lookup and drift check."""

import threading
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from numpy.typing import NDArray
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from dartscore.api.cameras import worker_or_404
from dartscore.vision import board
from dartscore.vision.calibration import (
    DRIFT_WARN_PX,
    BoardCalibration,
    CalibrationError,
    compute_overlay,
    delete_board,
    fit_homography,
    load_board,
    measure_drift,
    reference_file,
    save_board,
)
from dartscore.vision.intrinsics import Undistorter
from dartscore.vision.sources import Image

router = APIRouter(prefix="/api", tags=["calibration"])

Point = tuple[float, float]


class CalibrationStore:
    """Holds the board calibrations of all cameras plus their reference images."""

    def __init__(self, calibration_dir: Path, camera_ids: list[str]) -> None:
        self.dir = calibration_dir
        self._lock = threading.Lock()
        self._calibrations = {
            cid: cal for cid in camera_ids if (cal := load_board(calibration_dir, cid)) is not None
        }
        self._references: dict[str, Image | None] = {}
        # (timestamp, drift) per camera, so polling clients do not recompute constantly
        self._drift_cache: dict[str, tuple[float, float]] = {}
        # called after a calibration was saved or deleted (e.g. to rebuild the detector)
        self.on_change: Callable[[], None] | None = None

    def all(self) -> dict[str, BoardCalibration]:
        with self._lock:
            return dict(self._calibrations)

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def get(self, camera_id: str) -> BoardCalibration | None:
        with self._lock:
            return self._calibrations.get(camera_id)

    def save(self, calibration: BoardCalibration, reference: Image) -> None:
        save_board(calibration, self.dir, reference)
        with self._lock:
            self._calibrations[calibration.camera_id] = calibration
            self._references[calibration.camera_id] = reference
            self._drift_cache.pop(calibration.camera_id, None)
        self._changed()

    def delete(self, camera_id: str) -> None:
        delete_board(self.dir, camera_id)
        with self._lock:
            self._calibrations.pop(camera_id, None)
            self._references.pop(camera_id, None)
            self._drift_cache.pop(camera_id, None)
        self._changed()

    def reference(self, camera_id: str) -> Image | None:
        with self._lock:
            if camera_id not in self._references:
                path = reference_file(self.dir, camera_id)
                self._references[camera_id] = cv2.imread(str(path)) if path.is_file() else None
            return self._references[camera_id]

    def cached_drift(self, camera_id: str, max_age: float = 5.0) -> float | None:
        entry = self._drift_cache.get(camera_id)
        return entry[1] if entry and time.monotonic() - entry[0] < max_age else None

    def store_drift(self, camera_id: str, drift: float) -> None:
        self._drift_cache[camera_id] = (time.monotonic(), drift)


class CalibrationPointResponse(BaseModel):
    id: str
    x_mm: float
    y_mm: float


class CatalogResponse(BaseModel):
    required: int
    segments: list[int]
    points: list[CalibrationPointResponse]


class OverlayResponse(BaseModel):
    rings: list[list[Point]]
    wires: list[tuple[Point, Point]]
    labels: list[tuple[int, Point]]


class PointsRequest(BaseModel):
    points: dict[str, Point] = Field(description="image coordinates (px) per calibration point id")


class PreviewResponse(BaseModel):
    rms_px: float
    errors_px: dict[str, float]
    overlay: OverlayResponse


class CalibrationResponse(BaseModel):
    camera_id: str
    points: dict[str, Point]
    image_size: tuple[int, int]
    undistorted: bool
    rms_px: float
    created_at: str
    # lens calibration changed since this board calibration was made
    stale: bool
    # estimated shift of camera/board since calibration (px); None if not measurable
    drift_px: float | None
    drift_warning: bool
    overlay: OverlayResponse


class ScoreRequest(BaseModel):
    x: float
    y: float


class ScoreResponse(BaseModel):
    label: str
    segment: int
    multiplier: int
    points: int
    x_mm: float
    y_mm: float


def _store(request: Request) -> CalibrationStore:
    store: CalibrationStore = request.app.state.calibrations
    return store


def _undistorter(request: Request, camera_id: str) -> Undistorter | None:
    undistorters: dict[str, Undistorter] = request.app.state.undistorters
    return undistorters.get(camera_id)


def _overlay(homography: NDArray[np.float64]) -> OverlayResponse:
    o = compute_overlay(homography)
    return OverlayResponse(rings=o.rings, wires=o.wires, labels=o.labels)


def _current_image(request: Request, camera_id: str, undistorted: bool) -> Image | None:
    worker = worker_or_404(request, camera_id)
    # right after startup the first frame may still be on its way
    frame = worker.latest() or worker.wait_for_frame(0, 3.0)
    if frame is None:
        return None
    undistorter = _undistorter(request, camera_id)
    if undistorted and undistorter is not None:
        return undistorter.undistort(frame.image)
    return frame.image


def _calibration_or_404(request: Request, camera_id: str) -> BoardCalibration:
    worker_or_404(request, camera_id)
    calibration = _store(request).get(camera_id)
    if calibration is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} is not calibrated")
    return calibration


def _response(request: Request, calibration: BoardCalibration) -> CalibrationResponse:
    store = _store(request)
    cid = calibration.camera_id
    undistorter = _undistorter(request, cid)
    lens_created_at = undistorter.calibration.created_at if undistorter else None

    drift = store.cached_drift(cid)
    if drift is None:
        reference = store.reference(cid)
        current = _current_image(request, cid, calibration.undistorted)
        if reference is not None and current is not None:
            drift = measure_drift(reference, current)
            store.store_drift(cid, drift)

    return CalibrationResponse(
        camera_id=cid,
        points=calibration.points,
        image_size=calibration.image_size,
        undistorted=calibration.undistorted,
        rms_px=round(calibration.rms_px, 2),
        created_at=calibration.created_at,
        stale=calibration.lens_created_at != lens_created_at,
        drift_px=None if drift is None or not np.isfinite(drift) else round(drift, 1),
        drift_warning=drift is not None and drift > DRIFT_WARN_PX,
        overlay=_overlay(calibration.homography),
    )


@router.get("/calibration/points")
def calibration_points() -> CatalogResponse:
    return CatalogResponse(
        required=board.REQUIRED_POINTS,
        segments=list(board.SEGMENTS),
        points=[
            CalibrationPointResponse(id=p.id, x_mm=round(p.x_mm, 2), y_mm=round(p.y_mm, 2))
            for p in board.CALIBRATION_POINTS
        ],
    )


@router.get("/cameras/{camera_id}/calibration")
async def get_calibration(request: Request, camera_id: str) -> CalibrationResponse:
    calibration = _calibration_or_404(request, camera_id)
    return await run_in_threadpool(_response, request, calibration)


@router.post("/cameras/{camera_id}/calibration/preview")
def preview_calibration(request: Request, camera_id: str, body: PointsRequest) -> PreviewResponse:
    worker_or_404(request, camera_id)
    try:
        fit = fit_homography(body.points)
    except CalibrationError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    return PreviewResponse(
        rms_px=round(fit.rms_px, 2), errors_px=fit.errors_px, overlay=_overlay(fit.homography)
    )


@router.put("/cameras/{camera_id}/calibration")
async def save_calibration(
    request: Request, camera_id: str, body: PointsRequest
) -> CalibrationResponse:
    worker_or_404(request, camera_id)
    try:
        fit = fit_homography(body.points)
    except CalibrationError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from exc

    undistorter = _undistorter(request, camera_id)
    undistorted = undistorter is not None
    reference = await run_in_threadpool(_current_image, request, camera_id, undistorted)
    if reference is None:
        raise HTTPException(status_code=503, detail=f"Camera {camera_id} is not delivering images")
    h, w = reference.shape[:2]
    calibration = BoardCalibration(
        camera_id=camera_id,
        points=body.points,
        homography=fit.homography,
        image_size=(w, h),
        undistorted=undistorted,
        lens_created_at=undistorter.calibration.created_at if undistorter else None,
        rms_px=fit.rms_px,
    )
    await run_in_threadpool(_store(request).save, calibration, reference)
    return await run_in_threadpool(_response, request, calibration)


@router.delete("/cameras/{camera_id}/calibration", status_code=204)
def delete_calibration(request: Request, camera_id: str) -> None:
    worker_or_404(request, camera_id)
    _store(request).delete(camera_id)


@router.post("/cameras/{camera_id}/calibration/score")
def score(request: Request, camera_id: str, body: ScoreRequest) -> ScoreResponse:
    """Which field is at this image position? Used to verify a calibration by clicking."""
    calibration = _calibration_or_404(request, camera_id)
    result, (x_mm, y_mm) = calibration.score_at_pixel(body.x, body.y)
    return ScoreResponse(
        label=result.label,
        segment=result.segment,
        multiplier=result.multiplier,
        points=result.points,
        x_mm=round(x_mm, 1),
        y_mm=round(y_mm, 1),
    )
