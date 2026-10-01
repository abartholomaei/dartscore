"""A labeled test set of hand-placed darts for measuring the detection on close calls.

In normal games the truth of an uncorrected dart is whatever the detection said at the time,
which hides errors at the wires. Here the player places darts by hand in scenarios chosen to be
hard (a millimetre inside or outside a ring, next to a wire, angled, hidden by other darts) and
confirms the field each dart really is in. The label is stored as ``truth.json`` next to the
recording; replay prefers it over the game events (``dartscore replay --testset``).
"""

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dartscore.game.dart import BULL, MISS_SEGMENT, Dart
from dartscore.vision import board

TRUTH_FILE = "truth.json"


@dataclass(frozen=True)
class Scenario:
    id: str
    # what makes it hard; the frontend has a hint text per category and side
    category: str
    # where the dart goes: inside or outside the edge / left or right of the wire
    side: str
    target: str
    # the fields the dart can end up in; the player picks the real one
    candidates: tuple[str, ...]
    # where to put the tip (board mm, y up), for drawing it on a board: a little on the
    # target's side of the edge, so the marker is visible
    spot_mm: tuple[float, float] = (0.0, 0.0)


def _label(segment: int, multiplier: int) -> str:
    return Dart(segment, multiplier).label


# how far from the edge the marker is drawn (mm)
SPOT_OFFSET = 2.0


def _polar(r: float, deg: float) -> tuple[float, float]:
    return (round(r * math.cos(math.radians(deg)), 1), round(r * math.sin(math.radians(deg)), 1))


def _segment_deg(segment: int) -> float:
    """Board angle (0° = right, counterclockwise) of the middle of a segment."""
    return 90.0 - board.SEGMENTS.index(segment) * board.SEGMENT_ANGLE_DEG


def _ring(
    category: str, segments: tuple[int, ...], radius: float, inner: int, outer: int
) -> list[Scenario]:
    """Both sides of a ring edge at ``radius``, given by the multipliers on the bull side
    (``inner``) and the far side (``outer``, 0 = off the board)."""
    out = []
    for segment in segments:
        pair = (_label(segment, inner), _label(segment, outer) if outer else "MISS")
        for side, target, sign in (("inside", pair[0], -1), ("outside", pair[1], 1)):
            spot = _polar(radius + sign * SPOT_OFFSET, _segment_deg(segment))
            out.append(Scenario(f"{category}-{segment}-{side}", category, side, target, pair, spot))
    return out


def _catalog() -> list[Scenario]:
    scenarios: list[Scenario] = []
    # most detection errors are single <-> triple at the inner triple edge
    scenarios += _ring("triple_inner", (20, 1, 6, 10, 3, 19, 11, 14), board.R_TRIPLE_INNER, 1, 3)
    scenarios += _ring("triple_outer", (5, 17, 8, 12), board.R_TRIPLE_OUTER, 3, 1)
    scenarios += _ring("double_inner", (20, 6, 3, 11, 15, 7), board.R_DOUBLE_INNER, 1, 2)
    scenarios += _ring("double_outer", (13, 2, 16, 9), board.R_DOUBLE_OUTER, 2, 0)
    # side by side of a segment wire in the single area (left = counterclockwise side)
    r_wire = (board.R_TRIPLE_OUTER + board.R_DOUBLE_INNER) / 2
    for left, right in ((20, 1), (6, 10), (3, 19), (11, 14)):
        pair = (_label(left, 1), _label(right, 1))
        wire = _segment_deg(left) - board.SEGMENT_ANGLE_DEG / 2
        offset = math.degrees(SPOT_OFFSET / r_wire)
        for side, target, sign in (("left", pair[0], 1), ("right", pair[1], -1)):
            spot = _polar(r_wire, wire + sign * offset)
            scenarios.append(
                Scenario(f"wire-{left}-{right}-{side}", "wire", side, target, pair, spot)
            )
    # the bull rings
    for i, deg in ((1, 0.0), (2, 180.0)):
        pair = ("BULL", "25")
        for side, target, sign in (("inside", "BULL", -1), ("outside", "25", 1)):
            spot = _polar(board.R_BULL + sign * 1.5, deg)
            scenarios.append(Scenario(f"bull-{i}-{side}", "bull", side, target, pair, spot))
    for segment in (20, 3):
        pair = ("25", _label(segment, 1))
        for side, target, sign in (("inside", "25", -1), ("outside", pair[1], 1)):
            spot = _polar(board.R_OUTER_BULL + sign * 1.5, _segment_deg(segment))
            scenarios.append(
                Scenario(f"outer_bull-{segment}-{side}", "outer_bull", side, target, pair, spot)
            )
    # real throws enter at an angle: steeply angled darts at the inner triple edge of the 20
    angled_spot = _polar(board.R_TRIPLE_INNER + SPOT_OFFSET, 90.0)
    for side in ("left", "right", "up", "down"):
        scenarios.append(
            Scenario(f"angled-{side}", "angled", side, "T20", ("T20", "S20"), angled_spot)
        )
    # three darts close together, the later ones hiding the earlier ones from some cameras
    r_triple = (board.R_TRIPLE_INNER + board.R_TRIPLE_OUTER) / 2
    for i in range(1, 4):
        for n, deg in ((1, 87.0), (2, 90.0), (3, 93.0)):
            scenarios.append(
                Scenario(
                    f"cluster-{i}-{n}",
                    "cluster",
                    str(n),
                    "T20",
                    ("T20", "S20", "S1", "S5"),
                    _polar(r_triple, deg),
                )
            )
    return scenarios


SCENARIOS = _catalog()
SCENARIOS_BY_ID = {s.id: s for s in SCENARIOS}


def catalog() -> list[dict[str, Any]]:
    return [asdict(s) for s in SCENARIOS]


def parse_label(label: str) -> Dart:
    """``T20``, ``S5``, ``D16``, ``25``, ``BULL`` or ``MISS`` -> Dart."""
    text = label.strip().upper()
    if text == "MISS":
        return Dart(MISS_SEGMENT, 1)
    if text == "BULL":
        return Dart(BULL, 2)
    if text == "25":
        return Dart(BULL, 1)
    if len(text) >= 2 and text[0] in "SDT" and text[1:].isdigit():
        segment = int(text[1:])
        if 1 <= segment <= 20:
            return Dart(segment, "SDT".index(text[0]) + 1)
    raise ValueError(f"not a field: {label!r}")


def recording_folder(recordings_dir: Path, recording: str) -> Path:
    """The folder of a recording given as ``<day>/<time>``; refuses anything outside."""
    folder = (recordings_dir / recording).resolve()
    if recordings_dir.resolve() not in folder.parents or not (folder / "meta.json").is_file():
        raise FileNotFoundError(recording)
    return folder


def write_truth(folder: Path, dart: Dart, scenario: str | None) -> dict[str, Any]:
    truth = {
        "label": dart.label,
        "segment": dart.segment,
        "multiplier": dart.multiplier,
        "scenario": scenario,
        "labeled_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (folder / TRUTH_FILE).write_text(json.dumps(truth, indent=2))
    return truth


def read_truth(folder: Path) -> dict[str, Any] | None:
    path = folder / TRUTH_FILE
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def summary(recordings_dir: Path) -> dict[str, Any]:
    """How many darts are labeled, per category."""
    per_category: dict[str, int] = {}
    total = 0
    for path in recordings_dir.rglob(TRUTH_FILE):
        truth = json.loads(path.read_text())
        scenario = SCENARIOS_BY_ID.get(truth.get("scenario") or "")
        key = scenario.category if scenario else "other"
        per_category[key] = per_category.get(key, 0) + 1
        total += 1
    return {"total": total, "per_category": per_category}
