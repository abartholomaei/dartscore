"""Tournament endpoints."""

from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, model_validator

from dartscore.services.tournaments import TournamentService

router = APIRouter(prefix="/api/tournaments", tags=["tournaments"])


class Entry(BaseModel):
    player_id: int | None = None
    guest_name: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def exactly_one(self) -> "Entry":
        if (self.player_id is None) == (self.guest_name is None):
            raise ValueError("Give either player_id or guest_name")
        return self


class TournamentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    format: Literal["knockout", "round_robin"]
    mode: Literal["x01", "cricket"]
    settings: dict[str, Any] = Field(default_factory=dict)
    entries: list[Entry]
    shuffle: bool = False


def _service(request: Request) -> TournamentService:
    service: TournamentService = request.app.state.tournaments
    return service


@router.get("")
def overview(request: Request) -> list[dict[str, Any]]:
    return _service(request).overview()


@router.post("", status_code=201)
def create(request: Request, body: TournamentCreate) -> dict[str, Any]:
    entries = [e.model_dump(exclude_none=True) for e in body.entries]
    return _service(request).create(
        body.name, body.format, body.mode, body.settings, entries, body.shuffle
    )


@router.get("/by-game/{game_id}")
def for_game(request: Request, game_id: int) -> dict[str, Any] | None:
    return _service(request).for_game(game_id)


@router.get("/{tournament_id}")
def detail(request: Request, tournament_id: int) -> dict[str, Any]:
    return _service(request).get(tournament_id)


@router.post("/{tournament_id}/matches/{match_id}/start", status_code=201)
def start_match(request: Request, tournament_id: int, match_id: int) -> dict[str, Any]:
    return _service(request).start_match(tournament_id, match_id)


@router.delete("/{tournament_id}", status_code=204)
def delete(request: Request, tournament_id: int) -> Response:
    _service(request).delete(tournament_id)
    return Response(status_code=204)
