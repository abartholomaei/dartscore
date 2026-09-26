from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

from dartscore import __version__
from dartscore.api import cameras
from dartscore.config import Settings
from dartscore.vision.camera import CameraManager
from dartscore.vision.intrinsics import Undistorter, load_lens

log = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    status: str
    version: str
    cameras_configured: int


def load_undistorters(settings: Settings) -> dict[str, Undistorter]:
    undistorters = {}
    for cam in settings.cameras:
        lens = load_lens(settings.calibration_dir, cam.id)
        if lens is not None:
            undistorters[cam.id] = Undistorter(lens)
            log.info("lens_calibration_loaded", camera=cam.id, rms=round(lens.rms_error, 3))
    return undistorters


def create_app(settings: Settings, camera_manager: CameraManager | None = None) -> FastAPI:
    manager = camera_manager or CameraManager(settings.cameras)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        manager.start()
        try:
            yield
        finally:
            manager.stop()

    app = FastAPI(title="dartscore", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.cameras = manager
    app.state.jpeg = cameras.JpegRenderer(settings.stream, load_undistorters(settings))
    app.include_router(cameras.router)

    @app.get("/api/health")
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            cameras_configured=len(settings.cameras),
        )

    return app
