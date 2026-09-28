"""Checkout suggestions for X01: which darts finish a given remaining score."""

from functools import cache
from itertools import combinations_with_replacement
from typing import Literal

from dartscore.game.dart import BULL, Dart

InOutRule = Literal["single", "double", "master"]

# every dart that scores
SCORING_DARTS = tuple(
    [Dart(s, m) for s in range(1, 21) for m in (1, 2, 3)] + [Dart(BULL, 1), Dart(BULL, 2)]
)

# preferred finishing doubles (common "PDC" preferences), best first
_FINISH_ORDER = [20, 16, 8, 12, 10, 18, 4, 2, 6, 14, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, BULL]
# preferred setup darts, best first; anything else ranks after these
_SETUP_ORDER = [
    "T20", "T19", "T18", "T17", "T16", "T15", "S20", "S19", "S18", "S17", "S16", "S15",
    "BULL", "25", "T14", "T13", "T12", "T11", "T10",
]  # fmt: skip


def is_valid_finisher(dart: Dart, rule: InOutRule) -> bool:
    if dart.is_miss:
        return False
    if rule == "single":
        return True
    if rule == "double":
        return dart.is_double
    return dart.is_double or dart.is_triple


def is_valid_opener(dart: Dart, rule: InOutRule) -> bool:
    return is_valid_finisher(dart, rule)


def one_dart_finish(remaining: int, rule: InOutRule) -> bool:
    """Can `remaining` be finished with a single dart? (a checkout attempt, for statistics)"""
    return any(d.points == remaining and is_valid_finisher(d, rule) for d in SCORING_DARTS)


def _finish_rank(dart: Dart, rule: InOutRule) -> int:
    base = _FINISH_ORDER.index(dart.segment) if dart.segment in _FINISH_ORDER else 30
    # straight out: the big single is the easiest finish (20 left is S20, not D10);
    # otherwise prefer doubles, then trebles
    order = {1: 0, 2: 40, 3: 80} if rule == "single" else {2: 0, 3: 40, 1: 80}
    return base + order[dart.multiplier]


def _setup_rank(dart: Dart) -> int:
    if dart.label in _SETUP_ORDER:
        return _SETUP_ORDER.index(dart.label)
    # small singles are fine setup darts (e.g. S1 before D8), odd doubles/triples less so
    return 20 if dart.multiplier == 1 else 30 + (60 - dart.points) // 3


@cache
def suggest_checkout(
    remaining: int, darts_left: int = 3, rule: InOutRule = "double", preferred: int | None = None
) -> tuple[Dart, ...] | None:
    """Best route to finish `remaining` with at most `darts_left` darts, or None.
    ``preferred``: the player's favourite finishing double (segment), chosen when it needs no
    more darts than the best route."""
    if remaining <= 0 or darts_left <= 0:
        return None
    finishers = [d for d in SCORING_DARTS if is_valid_finisher(d, rule)]
    for count in range(1, darts_left + 1):
        best: tuple[int, tuple[Dart, ...]] | None = None
        best_preferred: tuple[int, tuple[Dart, ...]] | None = None
        for setup in combinations_with_replacement(SCORING_DARTS, count - 1):
            rest = remaining - sum(d.points for d in setup)
            for finisher in finishers:
                if finisher.points != rest:
                    continue
                # throw the biggest setup dart first
                ordered = tuple(sorted(setup, key=lambda d: (-d.points, _setup_rank(d))))
                rank = _finish_rank(finisher, rule) * 3 + sum(_setup_rank(d) for d in setup)
                route = (rank, (*ordered, finisher))
                if best is None or rank < best[0]:
                    best = route
                if (
                    finisher.segment == preferred
                    and finisher.is_double
                    and (best_preferred is None or rank < best_preferred[0])
                ):
                    best_preferred = route
        # the favourite double wins if it needs no more darts than the best route
        if best_preferred is not None:
            return best_preferred[1]
        if best is not None:
            return best[1]
    return None
