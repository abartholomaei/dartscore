"""Board geometry for the game logic (mm, origin at the bull, x right, y up)."""

import math

from dartscore.game.dart import BULL, Dart

# clockwise from the top
SEGMENTS = (20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5)
SEGMENT_ANGLE_DEG = 360 / len(SEGMENTS)
R_BULL = 6.35
R_OUTER_BULL = 15.9
R_TRIPLE_INNER = 99.0
R_TRIPLE_OUTER = 107.0
R_DOUBLE_INNER = 162.0
R_DOUBLE_OUTER = 170.0


def field_center(dart: Dart) -> tuple[float, float] | None:
    """The middle of the dart's field (used when the real position is unknown, e.g. a dart
    typed in by hand); None for a miss."""
    if dart.is_miss:
        return None
    if dart.segment == BULL:
        return (0.0, 0.0) if dart.multiplier == 2 else (0.0, (R_BULL + R_OUTER_BULL) / 2)
    angle = math.radians(90.0 - SEGMENTS.index(dart.segment) * SEGMENT_ANGLE_DEG)
    if dart.multiplier == 3:
        r = (R_TRIPLE_INNER + R_TRIPLE_OUTER) / 2
    elif dart.multiplier == 2:
        r = (R_DOUBLE_INNER + R_DOUBLE_OUTER) / 2
    else:
        r = (R_TRIPLE_OUTER + R_DOUBLE_INNER) / 2
    return r * math.cos(angle), r * math.sin(angle)
