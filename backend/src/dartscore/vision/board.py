"""Geometry of a standard steel-tip dartboard (dimensions in mm, origin = bullseye center).

Coordinates: x to the right, y up, angle 0° = right, counterclockwise.
The 20 is at the top (90°).
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from dartscore.game.dart import Dart

# segment order clockwise, starting at the top
SEGMENTS = (20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5)
SEGMENT_ANGLE_DEG = 360 / len(SEGMENTS)

# radii (outer edge) per WDF rules
R_BULL = 6.35
R_OUTER_BULL = 15.9
R_TRIPLE_INNER = 99.0
R_TRIPLE_OUTER = 107.0
R_DOUBLE_INNER = 162.0
R_DOUBLE_OUTER = 170.0
# board edge incl. number ring (for rendering only)
R_BOARD = 225.0

_BLACK = (30, 30, 30)
_CREAM = (200, 225, 235)
_RED = (40, 40, 200)
_GREEN = (60, 140, 40)
_WIRE = (180, 180, 180)


def segment_polygon(
    index: int, r_inner: float, r_outer: float, steps: int = 8
) -> NDArray[np.float64]:
    """Corner points (mm) of a ring segment; index 0 = the 20 at the top."""
    center = 90.0 - index * SEGMENT_ANGLE_DEG
    angles = np.radians(
        np.linspace(center + SEGMENT_ANGLE_DEG / 2, center - SEGMENT_ANGLE_DEG / 2, steps)
    )
    outer = np.stack([r_outer * np.cos(angles), r_outer * np.sin(angles)], axis=1)
    inner = np.stack([r_inner * np.cos(angles[::-1]), r_inner * np.sin(angles[::-1])], axis=1)
    return np.concatenate([outer, inner])


def mm_to_px(size_px: int) -> NDArray[np.float64]:
    """3x3 matrix: board coordinates (mm) → pixels of a square top-down image."""
    scale = size_px / (2 * R_BOARD)
    c = size_px / 2
    return np.array([[scale, 0, c], [0, -scale, c], [0, 0, 1]], dtype=np.float64)


def render_board(size_px: int = 900) -> NDArray[np.uint8]:
    """Draw the board top-down (BGR), e.g. for the simulated camera."""
    img = np.full((size_px, size_px, 3), 40, dtype=np.uint8)
    m = mm_to_px(size_px)

    def to_px(pts_mm: NDArray[np.float64]) -> NDArray[np.int32]:
        homog = np.column_stack([pts_mm, np.ones(len(pts_mm))]) @ m.T
        return np.round(homog[:, :2]).astype(np.int32)

    c = size_px // 2
    scale = m[0, 0]
    cv2.circle(img, (c, c), round(R_BOARD * scale), _BLACK, -1, cv2.LINE_AA)
    rings = (
        (R_DOUBLE_INNER, R_DOUBLE_OUTER, True),
        (R_TRIPLE_OUTER, R_DOUBLE_INNER, False),
        (R_TRIPLE_INNER, R_TRIPLE_OUTER, True),
        (R_OUTER_BULL, R_TRIPLE_INNER, False),
    )
    for i in range(len(SEGMENTS)):
        dark = i % 2 == 0
        for r_in, r_out, scoring_ring in rings:
            colors = (_RED, _GREEN) if scoring_ring else (_BLACK, _CREAM)
            color = colors[0] if dark else colors[1]
            cv2.fillPoly(img, [to_px(segment_polygon(i, r_in, r_out))], color, cv2.LINE_AA)
    cv2.circle(img, (c, c), round(R_OUTER_BULL * scale), _GREEN, -1, cv2.LINE_AA)
    cv2.circle(img, (c, c), round(R_BULL * scale), _RED, -1, cv2.LINE_AA)

    for r in (R_BULL, R_OUTER_BULL, R_TRIPLE_INNER, R_TRIPLE_OUTER, R_DOUBLE_INNER, R_DOUBLE_OUTER):
        cv2.circle(img, (c, c), round(r * scale), _WIRE, 1, cv2.LINE_AA)
    for i, number in enumerate(SEGMENTS):
        edge = math.radians(90.0 - (i + 0.5) * SEGMENT_ANGLE_DEG)
        direction = np.array([[math.cos(edge), math.sin(edge)]])
        p1 = to_px(R_OUTER_BULL * direction)[0]
        p2 = to_px(R_DOUBLE_OUTER * direction)[0]
        cv2.line(img, tuple(p1), tuple(p2), _WIRE, 1, cv2.LINE_AA)

        mid = math.radians(90.0 - i * SEGMENT_ANGLE_DEG)
        r_text = (R_DOUBLE_OUTER + R_BOARD) / 2
        pos = to_px(np.array([[r_text * math.cos(mid), r_text * math.sin(mid)]]))[0]
        text = str(number)
        font_scale = size_px / 900
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
        org = (int(pos[0] - tw / 2), int(pos[1] + th / 2))
        cv2.putText(
            img, text, org, cv2.FONT_HERSHEY_SIMPLEX, font_scale, (240, 240, 240), 2, cv2.LINE_AA
        )
    return img


# kept as an alias: the vision code speaks of scores, the game logic of darts
Score = Dart


def segment_at_angle(angle_deg: float) -> int:
    """Segment number for a board angle (0° = right, counterclockwise, like atan2)."""
    # clockwise angle from the top, shifted by half a segment so the 20 spans -9°..9°
    from_top = (90.0 - angle_deg + SEGMENT_ANGLE_DEG / 2) % 360.0
    return SEGMENTS[int(from_top // SEGMENT_ANGLE_DEG) % len(SEGMENTS)]


def score_at(x_mm: float, y_mm: float) -> Score:
    r = math.hypot(x_mm, y_mm)
    if r <= R_BULL:
        return Score(25, 2)
    if r <= R_OUTER_BULL:
        return Score(25, 1)
    if r > R_DOUBLE_OUTER:
        return Score.miss()
    segment = segment_at_angle(math.degrees(math.atan2(y_mm, x_mm)))
    if R_TRIPLE_INNER < r <= R_TRIPLE_OUTER:
        return Score(segment, 3)
    if r > R_DOUBLE_INNER:
        return Score(segment, 2)
    return Score(segment, 1)


@dataclass(frozen=True)
class CalibrationPoint:
    """A well-defined point on the board plane that users click in each camera image."""

    id: str
    x_mm: float
    y_mm: float


def _boundary_point(left: int, right: int) -> CalibrationPoint:
    """Where the outer edge of the double ring meets the wire between two segments."""
    i = SEGMENTS.index(left)
    assert SEGMENTS[(i + 1) % len(SEGMENTS)] == right, (left, right)
    angle = math.radians(90.0 - (i + 0.5) * SEGMENT_ANGLE_DEG)
    return CalibrationPoint(
        f"{left}/{right}", R_DOUBLE_OUTER * math.cos(angle), R_DOUBLE_OUTER * math.sin(angle)
    )


# Clicked in this order. The first four are 90° apart and required; the rest improve accuracy.
CALIBRATION_POINTS = (
    _boundary_point(20, 1),
    _boundary_point(6, 10),
    _boundary_point(3, 19),
    _boundary_point(11, 14),
    CalibrationPoint("bull", 0.0, 0.0),
    _boundary_point(4, 13),
    _boundary_point(15, 2),
    _boundary_point(7, 16),
    _boundary_point(9, 12),
)
REQUIRED_POINTS = 4
CALIBRATION_POINTS_BY_ID = {p.id: p for p in CALIBRATION_POINTS}
