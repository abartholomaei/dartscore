"""Practice modes of version 2: segment training and 121 checkout."""

import random
from dataclasses import dataclass, field
from typing import Any, Literal

from dartscore.game.base import Game, GameError, MatchSettings, Turn
from dartscore.game.checkout import suggest_checkout
from dartscore.game.dart import BULL, Dart
from dartscore.game.training import NUMBERS, _best

# --- Segment training ----------------------------------------------------------------------

Ring = Literal["any", "single", "double", "triple"]
RING_MULTIPLIER: dict[str, int | None] = {"any": None, "single": 1, "double": 2, "triple": 3}


@dataclass(frozen=True)
class SegmentTrainingSettings:
    # 1-20 or 25 (bull); 0 = a random target every turn
    number: int = 20
    ring: Ring = "any"
    # the session ends after `limit` hits or after `limit` darts
    end: Literal["hits", "darts"] = "darts"
    limit: int = 33
    seed: int = field(default_factory=lambda: random.randint(1, 1_000_000))

    def __post_init__(self) -> None:
        if self.number not in (0, *NUMBERS, BULL):
            raise GameError("invalid_settings", "number must be 1-20, 25 or 0 (random)")
        if self.number == BULL and self.ring == "triple":
            raise GameError("invalid_settings", "There is no triple bull")
        if self.end == "darts" and self.limit not in (33, 66, 99):
            raise GameError("invalid_settings", "darts limit must be 33, 66 or 99")
        if self.end == "hits" and not 1 <= self.limit <= 100:
            raise GameError("invalid_settings", "hits limit must be 1-100")


class SegmentTrainingGame(Game):
    """Aim at one segment (or a random one per turn). Ends after N hits (fewest darts wins) or
    after 33/66/99 darts (most hits wins)."""

    mode = "segment_training"

    def __init__(self, player_count: int, settings: SegmentTrainingSettings) -> None:
        self.settings = settings
        rng = random.Random(settings.seed)
        choices = [n for n in (*NUMBERS, BULL) if not (n == BULL and settings.ring == "triple")]
        # enough random targets for the longest possible session
        self._random_targets = [rng.choice(choices) for _ in range(400)]
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.hits = [0] * self.player_count
        self.darts = [0] * self.player_count
        self.hits_by_target: list[dict[int, int]] = [{} for _ in range(self.player_count)]

    def target_for(self, player: int, turn_index: int) -> int:
        if self.settings.number:
            return self.settings.number
        return self._random_targets[turn_index % len(self._random_targets)]

    def _done(self, player: int) -> bool:
        s = self.settings
        return (self.hits if s.end == "hits" else self.darts)[player] >= s.limit

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        if self._done(p):
            turn.values.append(0)
            turn.stop = True
            return
        target = self.target_for(p, self.turns_of(p).index(turn))
        required = RING_MULTIPLIER[self.settings.ring]
        if target == BULL and required == 1:
            required = None  # single bull: the outer bull; accept both bull rings
        hit = dart.segment == target and (required is None or dart.multiplier == required)
        self.darts[p] += 1
        turn.values.append(1 if hit else 0)
        if hit:
            self.hits[p] += 1
            self.hits_by_target[p][target] = self.hits_by_target[p].get(target, 0) + 1
        if self._done(p):
            turn.stop = True

    def _after_turn(self, turn: Turn) -> int | None:
        if not all(self._done(p) for p in range(self.player_count)):
            return None
        if self.settings.end == "hits":
            return _best([-float(d) for d in self.darts])
        return _best([float(h) for h in self.hits])

    def _next_player(self, player: int) -> int:
        # players who are finished are skipped
        for step in range(1, self.player_count + 1):
            candidate = (player + step) % self.player_count
            if not self._done(candidate):
                return candidate
        return (player + 1) % self.player_count

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.hits[player], "hits": self.hits[player]}

    def _label(self, target: int) -> str:
        if target == BULL:
            return "BULL" if self.settings.ring == "double" else "25"
        prefix = {"any": "", "single": "S", "double": "D", "triple": "T"}[self.settings.ring]
        return f"{prefix}{target}"

    def _leg_state(self) -> dict[str, Any]:
        p = self.current_player
        index = len(self.turns_of(p)) - (1 if self.current_turn is not None else 0)
        return {
            "target": self._label(self.target_for(p, index)),
            "hits": list(self.hits),
            "darts_thrown": list(self.darts),
            "limit": self.settings.limit,
            "end": self.settings.end,
            "hits_by_target": [{str(k): v for k, v in h.items()} for h in self.hits_by_target],
        }

    def settings_dict(self) -> dict[str, Any]:
        s = self.settings
        return {"number": s.number, "ring": s.ring, "end": s.end, "limit": s.limit, "seed": s.seed}


# --- 121 checkout --------------------------------------------------------------------------


@dataclass(frozen=True)
class Checkout121Settings:
    start: int = 121
    # attempts (each with darts_per_attempt darts) before the session ends
    attempts: int = 10
    darts_per_attempt: int = 9

    def __post_init__(self) -> None:
        if not 61 <= self.start <= 170 or suggest_checkout(self.start, 3, "double") is None:
            raise GameError("invalid_settings", "start must be a finishable score 61-170")
        if not 1 <= self.attempts <= 50:
            raise GameError("invalid_settings", "attempts must be 1-50")
        if self.darts_per_attempt not in (3, 6, 9):
            raise GameError("invalid_settings", "darts_per_attempt must be 3, 6 or 9")


def _next_finishable(score: int, step: int, floor: int) -> int:
    """The next score up (step 1) or down (step -1) that can be checked out in 3 darts."""
    candidate = score + step
    while 2 <= candidate <= 170:
        if candidate < floor:
            return floor
        if suggest_checkout(candidate, 3, "double") is not None:
            return candidate
        candidate += step
    return score


class Checkout121Game(Game):
    """Check out the target (double out) within 9 darts: success moves the target one up,
    failure one down (never below the start). The highest target checked out counts."""

    mode = "checkout_121"

    def __init__(self, player_count: int, settings: Checkout121Settings) -> None:
        self.settings = settings
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        n = self.player_count
        self.target = [self.settings.start] * n
        self.remaining = [self.settings.start] * n
        self.darts_on_target = [0] * n
        self.attempt = [0] * n
        self.successes = [0] * n
        self.best = [0] * n
        self.results: list[list[tuple[int, bool]]] = [[] for _ in range(n)]

    def _finished(self, p: int) -> bool:
        return self.attempt[p] >= self.settings.attempts

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        if self._finished(p):
            turn.values.append(0)
            turn.stop = True
            return
        self.darts_on_target[p] += 1
        new = self.remaining[p] - dart.points
        turn.values.append(dart.points)
        if new < 0 or new == 1 or (new == 0 and not dart.is_double):
            turn.bust = True
            self.remaining[p] += sum(turn.values[:-1])
        elif new == 0:
            self._end_attempt(p, success=True)
            turn.stop = True
            return
        else:
            self.remaining[p] = new
        if self.darts_on_target[p] >= self.settings.darts_per_attempt:
            self._end_attempt(p, success=False)
            turn.stop = True

    def _end_attempt(self, p: int, success: bool) -> None:
        self.results[p].append((self.target[p], success))
        self.attempt[p] += 1
        self.darts_on_target[p] = 0
        if success:
            self.successes[p] += 1
            self.best[p] = max(self.best[p], self.target[p])
        step = 1 if success else -1
        self.target[p] = _next_finishable(self.target[p], step, self.settings.start)
        self.remaining[p] = self.target[p]

    def _after_turn(self, turn: Turn) -> int | None:
        if all(self._finished(p) for p in range(self.player_count)):
            return _best([self.best[p] + self.successes[p] / 100 for p in range(self.player_count)])
        return None

    def _next_player(self, player: int) -> int:
        for step in range(1, self.player_count + 1):
            candidate = (player + step) % self.player_count
            if not self._finished(candidate):
                return candidate
        return (player + 1) % self.player_count

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.best[player], "hits": self.successes[player]}

    def _leg_state(self) -> dict[str, Any]:
        p = self.current_player
        turn = self.current_turn
        darts_left = min(
            3 - (len(turn.darts) if turn else 0),
            self.settings.darts_per_attempt - self.darts_on_target[p],
        )
        route = (
            suggest_checkout(self.remaining[p], max(darts_left, 1), "double")
            if not self._finished(p)
            else None
        )
        return {
            "target_score": list(self.target),
            "remaining": list(self.remaining),
            "attempt": [min(a + 1, self.settings.attempts) for a in self.attempt],
            "attempts": self.settings.attempts,
            "successes": list(self.successes),
            "best": list(self.best),
            "darts_on_target": list(self.darts_on_target),
            "checkout": [d.label for d in route] if route else None,
        }

    def settings_dict(self) -> dict[str, Any]:
        s = self.settings
        return {"start": s.start, "attempts": s.attempts, "darts_per_attempt": s.darts_per_attempt}
