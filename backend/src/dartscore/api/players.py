"""Player profile endpoints."""

from datetime import datetime

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from dartscore.services.players import PlayerService
from dartscore.storage.models import Player

router = APIRouter(prefix="/api/players", tags=["players"])

COLOR = r"^#[0-9a-fA-F]{6}$"


class PlayerResponse(BaseModel):
    id: int
    name: str
    color: str
    created_at: datetime
    archived: bool


class PlayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str | None = Field(default=None, pattern=COLOR)


class PlayerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = Field(default=None, pattern=COLOR)


def _service(request: Request) -> PlayerService:
    service: PlayerService = request.app.state.players
    return service


def _response(player: Player) -> PlayerResponse:
    return PlayerResponse(
        id=player.id,
        name=player.name,
        color=player.color,
        created_at=player.created_at,
        archived=player.archived_at is not None,
    )


@router.get("")
def list_players(request: Request, include_archived: bool = False) -> list[PlayerResponse]:
    return [_response(p) for p in _service(request).list(include_archived)]


@router.post("", status_code=201)
def create_player(request: Request, body: PlayerCreate) -> PlayerResponse:
    return _response(_service(request).create(body.name, body.color))


@router.get("/{player_id}")
def get_player(request: Request, player_id: int) -> PlayerResponse:
    return _response(_service(request).get(player_id))


@router.patch("/{player_id}")
def update_player(request: Request, player_id: int, body: PlayerUpdate) -> PlayerResponse:
    return _response(_service(request).update(player_id, body.name, body.color))


@router.delete("/{player_id}")
def delete_player(request: Request, player_id: int) -> Response:
    """204 if deleted; 200 with the archived player if it has games (statistics are kept)."""
    service = _service(request)
    if service.delete(player_id):
        return Response(status_code=204)
    return Response(
        content=_response(service.get(player_id)).model_dump_json(),
        media_type="application/json",
    )


@router.post("/{player_id}/restore")
def restore_player(request: Request, player_id: int) -> PlayerResponse:
    return _response(_service(request).restore(player_id))
