from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from dartscore import __version__
from dartscore.api import calibration, cameras
from dartscore.config import Settings
from dartscore.vision.camera import CameraManager
from dartscore.vision.intrinsics import Undistorter, load_lens

log = structlog.get_logger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serves the frontend; unknown paths (e.g. /cameras) get index.html
    so client-side routing works."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


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
    # shared by the stream renderer and the calibration endpoints
    app.state.undistorters = load_undistorters(settings)
    app.state.jpeg = cameras.JpegRenderer(settings.stream, app.state.undistorters)
    app.state.calibrations = calibration.CalibrationStore(
        settings.calibration_dir, [c.id for c in settings.cameras]
    )
    app.include_router(cameras.router)
    app.include_router(calibration.router)

    @app.get("/api/health")
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            cameras_configured=len(settings.cameras),
        )

    # mount last so /api/... takes precedence
    if (settings.frontend_dir / "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
        log.info("serving_frontend", path=str(settings.frontend_dir))

    return app
