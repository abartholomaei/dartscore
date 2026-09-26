"""Statistics endpoints."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response

from dartscore.services.export import ExportService
from dartscore.services.stats import StatsService, player_positions

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _service(request: Request) -> StatsService:
    service: StatsService = request.app.state.stats
    return service


Days = Annotated[int | None, Query(ge=1, le=3650)]


@router.get("/players/{player_id}")
def player_stats(request: Request, player_id: int, days: Days = None) -> dict[str, Any]:
    return _service(request).player(player_id, days)


@router.get("/players/{player_id}/doubles")
def double_rates(request: Request, player_id: int, days: Days = None) -> dict[str, dict[str, int]]:
    """Attempts and hits per double (checkout attempts, doubles training, Bob's 27)."""
    exports: ExportService = request.app.state.exports
    return exports.double_rates(player_id, days)


@router.get("/head-to-head")
def head_to_head(request: Request, a: int, b: int) -> dict[str, Any]:
    return _service(request).head_to_head(a, b)


@router.get("/players/{player_id}/positions")
def positions(request: Request, player_id: int) -> list[tuple[float, float, str]]:
    """Positions of detected darts for the heatmap."""
    return player_positions(request.app.state.sessions, player_id)


export_router = APIRouter(prefix="/api/export", tags=["export"])


def _download(content: str, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@export_router.get("/games.csv")
def export_games(request: Request) -> Response:
    exports: ExportService = request.app.state.exports
    return _download(exports.games_csv(), "dartscore-games.csv", "text/csv")


@export_router.get("/darts.csv")
def export_darts(request: Request) -> Response:
    exports: ExportService = request.app.state.exports
    return _download(exports.darts_csv(), "dartscore-darts.csv", "text/csv")


@export_router.get("/all.json")
def export_all(request: Request) -> Response:
    exports: ExportService = request.app.state.exports
    return _download(
        json.dumps(exports.all_json(), indent=1), "dartscore-export.json", "application/json"
    )
