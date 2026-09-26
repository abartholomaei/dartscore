"""Statistics endpoints."""

from typing import Any

from fastapi import APIRouter, Request

from dartscore.services.stats import StatsService

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _service(request: Request) -> StatsService:
    service: StatsService = request.app.state.stats
    return service


@router.get("/players/{player_id}")
def player_stats(request: Request, player_id: int) -> dict[str, Any]:
    return _service(request).player(player_id)


@router.get("/head-to-head")
def head_to_head(request: Request, a: int, b: int) -> dict[str, Any]:
    return _service(request).head_to_head(a, b)
