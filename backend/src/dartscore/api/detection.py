"""Detection endpoints: status, on/off, reset, and a simulator for synthetic cameras."""

import math
import random
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dartscore.config import Settings
from dartscore.services.detection import DetectionService
from dartscore.vision import board
from dartscore.vision.sources import SIMULATED_BOARD

router = APIRouter(prefix="/api", tags=["detection"])


class DetectionUpdate(BaseModel):
    enabled: bool


class SimulatorAction(BaseModel):
    action: Literal["dart", "random", "clear", "hand"]
    x_mm: float | None = None
    y_mm: float | None = None
    on: bool | None = None


def _service(request: Request) -> DetectionService:
    service: DetectionService = request.app.state.detection
    return service


@router.get("/detection")
def detection_status(request: Request) -> dict[str, Any]:
    return _service(request).status()


@router.put("/detection")
def update_detection(request: Request, body: DetectionUpdate) -> dict[str, Any]:
    _service(request).set_enabled(body.enabled)
    return _service(request).status()


@router.post("/detection/reset")
def reset_detection(request: Request) -> dict[str, Any]:
    """Takes the current board as the new empty reference (e.g. after clearing it by hand)."""
    _service(request).reset()
    return _service(request).status()


@router.post("/simulator")
def simulate(request: Request, body: SimulatorAction) -> dict[str, Any]:
    """Only for synthetic cameras: put darts into the simulated board, clear it, show a hand."""
    settings: Settings = request.app.state.settings
    if not any(c.source == "synthetic" for c in settings.cameras):
        raise HTTPException(status_code=404, detail="No synthetic cameras configured")
    if body.action == "dart":
        if body.x_mm is None or body.y_mm is None:
            raise HTTPException(status_code=422, detail="x_mm and y_mm required")
        SIMULATED_BOARD.darts.append((body.x_mm, body.y_mm))
    elif body.action == "random":
        # mostly into the scoring area, sometimes a triple or the bull
        r = random.choice([random.uniform(20, 160), 103.0, random.uniform(0, 15)])
        a = random.uniform(0, 2 * math.pi)
        SIMULATED_BOARD.darts.append((r * math.cos(a), r * math.sin(a)))
    elif body.action == "clear":
        SIMULATED_BOARD.darts.clear()
    else:
        SIMULATED_BOARD.hand = bool(body.on)
    x, y = SIMULATED_BOARD.darts[-1] if SIMULATED_BOARD.darts else (0.0, 0.0)
    return {
        "darts": len(SIMULATED_BOARD.darts),
        "hand": SIMULATED_BOARD.hand,
        "last": board.score_at(x, y).label if SIMULATED_BOARD.darts else None,
    }
