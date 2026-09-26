from fastapi import FastAPI
from pydantic import BaseModel

from dartscore import __version__
from dartscore.config import Settings


class HealthResponse(BaseModel):
    status: str
    version: str
    cameras_configured: int


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="dartscore", version=__version__)
    app.state.settings = settings

    @app.get("/api/health")
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            cameras_configured=len(settings.cameras),
        )

    return app
