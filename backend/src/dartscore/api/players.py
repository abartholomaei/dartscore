"""Player profile endpoints."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, Field, field_validator

from dartscore.services.players import PlayerService
from dartscore.storage.models import Player

router = APIRouter(prefix="/api/players", tags=["players"])

COLOR = r"^#[0-9a-fA-F]{6}$"


Mode = Literal[
    "x01",
    "cricket",
    "around_the_clock",
    "shanghai",
    "bobs_27",
    "checkout_training",
    "doubles_training",
    "killer",
    "halve_it",
    "gotcha",
    "score_training",
]
# the current PIN of a protected profile, sent with changes
PinHeader = Annotated[str | None, Header()]
FavoriteDouble = Annotated[int, Field(ge=1, le=25)]


class PlayerResponse(BaseModel):
    id: int
    name: str
    color: str
    created_at: datetime
    archived: bool
    favorite_double: int | None
    throwing_hand: Literal["right", "left"] | None
    default_mode: Mode | None
    has_pin: bool


class PlayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str | None = Field(default=None, pattern=COLOR)


class PlayerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = Field(default=None, pattern=COLOR)
    favorite_double: FavoriteDouble | None = None
    throwing_hand: Literal["right", "left"] | None = None
    default_mode: Mode | None = None
    # set a PIN (4-8 digits) or remove it with null
    new_pin: str | None = Field(default=None, pattern=r"^\d{4,8}$")

    @field_validator("favorite_double")
    @classmethod
    def valid_double(cls, value: int | None) -> int | None:
        if value is not None and not (1 <= value <= 20 or value == 25):
            raise ValueError("favorite_double must be 1-20 or 25 (bull)")
        return value


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
        favorite_double=player.favorite_double,
        throwing_hand=player.throwing_hand,
        default_mode=player.default_mode,
        has_pin=player.pin_hash is not None,
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
def update_player(
    request: Request, player_id: int, body: PlayerUpdate, x_player_pin: PinHeader = None
) -> PlayerResponse:
    # only the preferences actually sent are changed (null clears one)
    preferences: dict[str, object] = {
        key: getattr(body, key)
        for key in ("favorite_double", "throwing_hand", "default_mode")
        if key in body.model_fields_set
    }
    new_pin = body.new_pin if "new_pin" in body.model_fields_set else False
    return _response(
        _service(request).update(
            player_id, body.name, body.color, preferences, x_player_pin, new_pin
        )
    )


@router.delete("/{player_id}")
def delete_player(request: Request, player_id: int, x_player_pin: PinHeader = None) -> Response:
    """204 if deleted; 200 with the archived player if it has games (statistics are kept)."""
    service = _service(request)
    if service.delete(player_id, x_player_pin):
        return Response(status_code=204)
    return Response(
        content=_response(service.get(player_id)).model_dump_json(),
        media_type="application/json",
    )


@router.post("/{player_id}/restore")
def restore_player(request: Request, player_id: int) -> PlayerResponse:
    return _response(_service(request).restore(player_id))
