"""Game endpoints: start, throw, next, undo, correct, abort, rematch, history."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from dartscore.game import Dart, GameError
from dartscore.services.games import GameService, PlayerRef
from dartscore.services.recordings import RecordingIndex

router = APIRouter(prefix="/api/games", tags=["games"])

GameState = dict[str, Any]


class Participant(BaseModel):
    player_id: int | None = None
    guest_name: str | None = Field(default=None, max_length=40)
    # a computer opponent with this target 3-dart average
    bot_level: int | None = Field(default=None, ge=20, le=120)

    @model_validator(mode="after")
    def exactly_one(self) -> "Participant":
        given = [self.player_id, self.guest_name, self.bot_level]
        if sum(value is not None for value in given) != 1:
            raise ValueError("Give one of player_id, guest_name or bot_level")
        return self


class GameCreate(BaseModel):
    mode: Literal[
        "x01",
        "cricket",
        "around_the_clock",
        "shanghai",
        "bobs_27",
        "checkout_training",
        "doubles_training",
        "bull_off",
        "killer",
        "halve_it",
        "gotcha",
        "score_training",
        "segment_training",
        "checkout_121",
    ]
    settings: dict[str, Any] = {}
    players: list[Participant] = Field(min_length=1, max_length=8)
    # end a running game instead of failing with 409
    abort_active: bool = False


class DartInput(BaseModel):
    """A dart as label ('T20', 'D16', '25', 'BULL', 'MISS') or as segment + multiplier."""

    dart: str | None = None
    segment: int | None = None
    multiplier: int | None = None

    def to_dart(self) -> Dart:
        try:
            if self.dart is not None:
                return Dart.parse(self.dart)
            if self.segment is not None:
                multiplier = self.multiplier if self.multiplier is not None else 1
                return Dart(self.segment, 0 if self.segment == 0 else multiplier)
        except ValueError as exc:
            raise GameError("invalid_dart", str(exc)) from exc
        raise GameError("invalid_dart", "Give dart or segment")


class DartCorrection(DartInput):
    turn_index: int
    dart_index: int
    # the dart fell out of the board: scores nothing, the detection itself was right
    bounce: bool = False

    def to_dart(self) -> Dart:
        return Dart.miss() if self.bounce else super().to_dart()


def _service(request: Request) -> GameService:
    service: GameService = request.app.state.games
    return service


@router.get("")
def history(request: Request, limit: int = 20, player_id: int | None = None) -> list[GameState]:
    return _service(request).history(min(limit, 200), player_id)


@router.post("", status_code=201)
def create_game(request: Request, body: GameCreate) -> GameState:
    refs = [PlayerRef(p.player_id, p.guest_name, p.bot_level) for p in body.players]
    return _service(request).create(body.mode, body.settings, refs, body.abort_active)


@router.get("/active")
def active_game(request: Request) -> GameState | None:
    return _service(request).active_state()


@router.post("/active/throws")
def throw(request: Request, body: DartInput) -> GameState:
    return _service(request).throw(body.to_dart(), source="manual")


@router.post("/active/next")
def next_turn(request: Request) -> GameState:
    return _service(request).next_turn()


@router.post("/active/undo")
def undo(request: Request) -> GameState:
    return _service(request).undo()


@router.put("/active/darts")
def correct(request: Request, body: DartCorrection) -> GameState:
    return _service(request).correct(
        body.turn_index, body.dart_index, body.to_dart(), bounce=body.bounce
    )


@router.post("/active/abort", status_code=204)
def abort(request: Request) -> None:
    _service(request).abort()


@router.post("/rematch", status_code=201)
def rematch(request: Request) -> GameState:
    return _service(request).rematch()


class PlayOn(BaseModel):
    legs_to_win: int = Field(ge=1, le=21)
    sets_to_win: int = Field(ge=1, le=13)


@router.post("/play-on")
def play_on(request: Request, body: PlayOn) -> GameState:
    """Continue the last finished match with a higher target."""
    return _service(request).play_on(body.legs_to_win, body.sets_to_win)


@router.get("/{game_id}/visits")
def visits(request: Request, game_id: int) -> list[dict[str, Any]]:
    """All turns with the recorded camera images of their darts."""
    recordings: RecordingIndex = request.app.state.recordings
    result = _service(request).visits(game_id)
    for visit in result:
        photos: list[dict[str, Any] | None] = []
        for seq in visit["seqs"]:
            found = recordings.get(game_id, seq) if seq is not None else None
            if found is None:
                photos.append(None)
                continue
            detection = found[1].get("detection") or {}
            photos.append(
                {
                    "cameras": sorted(c for c in (found[1].get("calibrations") or {})),
                    "tips": {h["camera_id"]: h["tip_px"] for h in detection.get("hits", [])},
                    "used": [h["camera_id"] for h in detection.get("hits", []) if h.get("used")],
                    "detected": detection.get("label"),
                }
            )
        visit["photos"] = photos
    return result


@router.get("/{game_id}/darts/{seq}/{camera_id}.jpg")
def dart_photo(
    request: Request, game_id: int, seq: int, camera_id: str, kind: str = "after"
) -> FileResponse:
    recordings: RecordingIndex = request.app.state.recordings
    path = recordings.image_path(game_id, seq, camera_id, kind)
    if path is None:
        raise HTTPException(status_code=404, detail="No photo for this dart")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@router.get("/{game_id}")
def get_game(request: Request, game_id: int) -> GameState:
    return _service(request).game_state(game_id)
