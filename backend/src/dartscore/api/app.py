import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from dartscore import __version__
from dartscore.api import calibration, cameras, detection, games, players, stats, ws
from dartscore.config import Settings
from dartscore.game import GameError
from dartscore.services.achievements import AchievementService
from dartscore.services.bot import BotService
from dartscore.services.calibration_monitor import CalibrationMonitor
from dartscore.services.detection import DetectionService
from dartscore.services.export import ExportService
from dartscore.services.games import GameService
from dartscore.services.hub import EventHub
from dartscore.services.players import PlayerService
from dartscore.services.stats import StatsService
from dartscore.storage.backup import DailyBackup
from dartscore.storage.db import create_db_engine, database_url, migrate, session_factory
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


# error codes that mean "does not exist" or "conflicts with the current state"
_NOT_FOUND = {"player_not_found", "game_not_found", "no_active_game", "no_game"}
_CONFLICT = {"game_active", "name_taken"}
_FORBIDDEN = {"pin_required", "wrong_pin"}


def _game_error_status(code: str) -> int:
    if code in _NOT_FOUND:
        return 404
    if code in _CONFLICT:
        return 409
    if code in _FORBIDDEN:
        return 403
    return 422


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
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(database_url(settings.data_dir))
    migrate(engine)
    sessions = session_factory(engine)
    hub = EventHub()
    backups = DailyBackup(settings.data_dir / "dartscore.db", settings.data_dir / "backups")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        hub.bind(asyncio.get_running_loop())
        manager.start()
        detection_service.start()
        backups.start()
        monitor.start()
        bots.start()
        try:
            yield
        finally:
            bots.stop()
            monitor.stop()
            backups.stop()
            detection_service.stop()
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
    app.state.hub = hub
    app.state.sessions = sessions
    app.state.players = PlayerService(sessions)
    app.state.games = GameService(sessions, hub)
    bots = app.state.bots = BotService(app.state.games)
    app.state.stats = StatsService(sessions)
    app.state.exports = ExportService(sessions)
    app.state.achievements = AchievementService(sessions)
    detection_service = DetectionService(
        settings.detection,
        manager,
        app.state.games,
        hub,
        settings.recordings_dir,
        settings.model_file,
    )
    app.state.detection = detection_service

    def reconfigure_detection() -> None:
        store: calibration.CalibrationStore = app.state.calibrations
        detection_service.configure(store.all(), app.state.undistorters)

    app.state.calibrations.on_change = reconfigure_detection
    reconfigure_detection()
    monitor = CalibrationMonitor(
        settings.detection,
        app.state.calibrations.all,
        app.state.calibrations.realign,
        manager,
        app.state.undistorters,
        detection_service.status,
        hub,
    )
    app.state.calibration_monitor = monitor
    for module in (cameras, calibration, players, games, stats, detection, ws):
        app.include_router(module.router)
    app.include_router(stats.export_router)

    @app.exception_handler(GameError)
    async def game_error(_request: Request, exc: GameError) -> JSONResponse:
        return JSONResponse(
            status_code=_game_error_status(exc.code),
            content={"detail": {"code": exc.code, "message": str(exc)}},
        )

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
