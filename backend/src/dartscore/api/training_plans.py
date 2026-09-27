"""Training plan endpoints."""

from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from dartscore.services.training_plans import TrainingPlanService

router = APIRouter(prefix="/api", tags=["training plans"])


def _service(request: Request) -> TrainingPlanService:
    service: TrainingPlanService = request.app.state.training_plans
    return service


class PlanChoice(BaseModel):
    plan: str


@router.get("/training-plans")
def catalog(request: Request) -> list[dict[str, Any]]:
    return _service(request).catalog()


@router.get("/players/{player_id}/training-plan")
def current(request: Request, player_id: int) -> dict[str, Any] | None:
    return _service(request).current(player_id)


@router.put("/players/{player_id}/training-plan")
def start(request: Request, player_id: int, body: PlanChoice) -> dict[str, Any]:
    return _service(request).start(player_id, body.plan)


@router.delete("/players/{player_id}/training-plan", status_code=204)
def stop(request: Request, player_id: int) -> Response:
    _service(request).stop(player_id)
    return Response(status_code=204)


@router.post(
    "/players/{player_id}/training-plan/sessions/{session}/drills/{drill}/start", status_code=201
)
def start_drill(request: Request, player_id: int, session: int, drill: int) -> dict[str, Any]:
    return _service(request).start_drill(player_id, session, drill)
