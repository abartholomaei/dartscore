"""Test set of hand-placed darts: the scenarios and labeling a recorded dart (vision.testset)."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dartscore.config import Settings
from dartscore.vision import testset

router = APIRouter(prefix="/api/testset", tags=["test set"])


class LabelRequest(BaseModel):
    # the dart's recording folder as sent with the detection ("<day>/<time>")
    recording: str
    # the field the dart really is in, e.g. "T20", "25", "BULL", "MISS"
    label: str
    scenario: str | None = None


def _recordings_dir(request: Request) -> Path:
    settings: Settings = request.app.state.settings
    return settings.recordings_dir


@router.get("/scenarios")
def scenarios() -> list[dict[str, Any]]:
    return testset.catalog()


@router.get("/summary")
def summary(request: Request) -> dict[str, Any]:
    return testset.summary(_recordings_dir(request))


@router.post("/labels")
def label(request: Request, body: LabelRequest) -> dict[str, Any]:
    try:
        dart = testset.parse_label(body.label)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.scenario is not None and body.scenario not in testset.SCENARIOS_BY_ID:
        raise HTTPException(422, f"unknown scenario: {body.scenario}")
    try:
        folder = testset.recording_folder(_recordings_dir(request), body.recording)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"no recording {body.recording}") from exc
    return testset.write_truth(folder, dart, body.scenario)
