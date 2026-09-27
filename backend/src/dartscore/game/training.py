"""Training and party modes: Around the Clock, Shanghai, Bob's 27, checkout and doubles training.

All of them are played as a single leg; the winner is decided by the mode's own score.
"""

import random
from dataclasses import dataclass, field
from typing import Any, Literal

from dartscore.game.base import Game, GameError, MatchSettings, Turn
from dartscore.game.checkout import suggest_checkout
from dartscore.game.dart import BULL, Dart

NUMBERS = tuple(range(1, 21))
# the numbers clockwise around the board, starting at the top
BOARD_ORDER = (20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5)


def _target_label(target: int, multiplier: int | None) -> str:
    if target == BULL:
        return "BULL" if multiplier == 2 else "25"
    prefix = {None: "", 1: "S", 2: "D", 3: "T"}[multiplier]
    return f"{prefix}{target}"


def _best(values: list[float]) -> int:
    """Index of the highest value (the first one on ties)."""
    return max(range(len(values)), key=lambda i: (values[i], -i))


# --- Around the Clock ----------------------------------------------------------------------


@dataclass(frozen=True)
class AroundTheClockSettings:
    # which ring counts: any segment, only doubles or only triples
    variant: Literal["single", "double", "triple"] = "single"
    # (single variant) a double/triple of the target advances by two/three numbers
    skip_multiples: bool = False
    include_bull: bool = True
    # "board": clockwise around the board from the 20 ("Round the World")
    order: Literal["numbers", "board"] = "numbers"


class AroundTheClockGame(Game):
    mode = "around_the_clock"

    def __init__(self, player_count: int, settings: AroundTheClockSettings) -> None:
        self.settings = settings
        numbers = BOARD_ORDER if settings.order == "board" else NUMBERS
        self.targets = numbers + ((BULL,) if settings.include_bull else ())
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.position = [0] * self.player_count
        self.hits = [0] * self.player_count

    def _required_multiplier(self, target: int) -> int | None:
        variant = self.settings.variant
        if variant == "single":
            return None
        if target == BULL:
            # there is no triple bull: the double bull counts in both variants
            return 2
        return 2 if variant == "double" else 3

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        target = self.targets[self.position[p]]
        required = self._required_multiplier(target)
        hit = dart.segment == target and (required is None or dart.multiplier == required)
        turn.values.append(1 if hit else 0)
        if not hit:
            return
        self.hits[p] += 1
        step = (
            dart.multiplier
            if self.settings.skip_multiples and required is None and target != BULL
            else 1
        )
        self.position[p] = min(self.position[p] + step, len(self.targets))
        if self.position[p] >= len(self.targets):
            turn.checkout = True

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.position[player], "hits": self.hits[player]}

    def _leg_state(self) -> dict[str, Any]:
        return {
            "targets": list(self.targets),
            "position": list(self.position),
            "current_targets": [
                _target_label(self.targets[pos], self._required_multiplier(self.targets[pos]))
                if pos < len(self.targets)
                else None
                for pos in self.position
            ],
        }

    def settings_dict(self) -> dict[str, Any]:
        return {
            "variant": self.settings.variant,
            "skip_multiples": self.settings.skip_multiples,
            "include_bull": self.settings.include_bull,
            "order": self.settings.order,
        }


# --- Shanghai ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ShanghaiSettings:
    rounds: int = 7

    def __post_init__(self) -> None:
        if not 1 <= self.rounds <= 20:
            raise GameError("invalid_settings", "rounds must be 1-20")


class ShanghaiGame(Game):
    mode = "shanghai"

    def __init__(self, player_count: int, settings: ShanghaiSettings) -> None:
        self.settings = settings
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.scores = [0] * self.player_count

    def _round(self, turn: Turn) -> int:
        return self.turns_of(turn.player).index(turn) + 1

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        target = self._round(turn)
        points = dart.points if dart.segment == target else 0
        turn.values.append(points)
        self.scores[turn.player] += points
        hit_multipliers = {d.multiplier for d in turn.darts if d.segment == target}
        if hit_multipliers >= {1, 2, 3}:
            turn.checkout = True  # Shanghai: single, double and triple of the number

    def _after_turn(self, turn: Turn) -> int | None:
        rounds = self.settings.rounds
        if all(len(self.turns_of(p)) >= rounds for p in range(self.player_count)):
            return _best([float(s) for s in self.scores])
        return None

    def player_result(self, player: int) -> dict[str, int]:
        hits = sum(1 for t in self.turns_of(player, self.legs[0]) for v in t.values if v)
        return {"score": self.scores[player], "hits": hits}

    def _leg_state(self) -> dict[str, Any]:
        current = len(self.turns_of(self.current_player))
        turn = self.current_turn
        round_no = current if turn is not None else current + 1
        return {
            "scores": list(self.scores),
            "round": min(round_no, self.settings.rounds),
            "rounds": self.settings.rounds,
        }

    def settings_dict(self) -> dict[str, Any]:
        return {"rounds": self.settings.rounds}


# --- Bob's 27 ------------------------------------------------------------------------------

BOBS_TARGETS = (*NUMBERS, BULL)


@dataclass(frozen=True)
class BobsSettings:
    start: int = 27


class BobsGame(Game):
    mode = "bobs_27"

    def __init__(self, player_count: int, settings: BobsSettings) -> None:
        self.settings = settings
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.scores = [self.settings.start] * self.player_count
        self.out = [False] * self.player_count
        self.hits = [0] * self.player_count

    def _target(self, turn: Turn) -> int:
        index = self.turns_of(turn.player).index(turn)
        return BOBS_TARGETS[min(index, len(BOBS_TARGETS) - 1)]

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        target = self._target(turn)
        hit = dart.segment == target and dart.multiplier == 2 and not self.out[turn.player]
        value = 2 * target if hit else 0
        turn.values.append(value)
        if hit:
            self.scores[turn.player] += value
            self.hits[turn.player] += 1

    def _after_turn(self, turn: Turn) -> int | None:
        p = turn.player
        if not self.out[p] and not any(turn.values):
            self.scores[p] -= 2 * self._target(turn)
            if self.scores[p] <= 0:
                self.out[p] = True
        done = [
            self.out[q] or len(self.turns_of(q)) >= len(BOBS_TARGETS)
            for q in range(self.player_count)
        ]
        if all(done):
            return _best([float(s) for s in self.scores])
        return None

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.scores[player], "hits": self.hits[player]}

    def _leg_state(self) -> dict[str, Any]:
        rounds = len(self.turns_of(self.current_player))
        if self.current_turn is not None:
            rounds -= 1
        index = min(rounds, len(BOBS_TARGETS) - 1)
        return {
            "scores": list(self.scores),
            "out": list(self.out),
            "target": _target_label(BOBS_TARGETS[index], 2),
            "round": index + 1,
            "rounds": len(BOBS_TARGETS),
        }

    def settings_dict(self) -> dict[str, Any]:
        return {"start": self.settings.start}


# --- Checkout training ---------------------------------------------------------------------


@dataclass(frozen=True)
class CheckoutTrainingSettings:
    count: int = 10
    min_score: int = 41
    max_score: int = 170
    darts_per_target: int = 9
    seed: int = field(default_factory=lambda: random.randint(1, 1_000_000))

    def __post_init__(self) -> None:
        if not (2 <= self.min_score <= self.max_score <= 170 and 1 <= self.count <= 50):
            raise GameError("invalid_settings", "Invalid checkout training range")
        if self.darts_per_target not in (3, 6, 9, 12):
            raise GameError("invalid_settings", "darts_per_target must be 3, 6, 9 or 12")


class CheckoutTrainingGame(Game):
    mode = "checkout_training"

    def __init__(self, player_count: int, settings: CheckoutTrainingSettings) -> None:
        self.settings = settings
        rng = random.Random(settings.seed)
        finishable = [
            n
            for n in range(settings.min_score, settings.max_score + 1)
            if suggest_checkout(n, 3, "double") is not None
        ]
        self.targets = [rng.choice(finishable) for _ in range(settings.count)]
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        n = self.player_count
        self.index = [0] * n
        self.remaining = [self.targets[0]] * n
        self.darts_on_target = [0] * n
        self.successes = [0] * n
        self.results: list[list[bool]] = [[] for _ in range(n)]

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        if self.index[p] >= len(self.targets):
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
            self._next_target(p, success=True)
            turn.stop = True
            return
        else:
            self.remaining[p] = new
        if self.darts_on_target[p] >= self.settings.darts_per_target:
            self._next_target(p, success=False)
            turn.stop = True

    def _next_target(self, p: int, success: bool) -> None:
        self.results[p].append(success)
        self.successes[p] += int(success)
        self.index[p] += 1
        self.darts_on_target[p] = 0
        if self.index[p] < len(self.targets):
            self.remaining[p] = self.targets[self.index[p]]

    def _after_turn(self, turn: Turn) -> int | None:
        if all(i >= len(self.targets) for i in self.index):
            return _best([float(s) for s in self.successes])
        return None

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.successes[player], "hits": self.successes[player]}

    def _leg_state(self) -> dict[str, Any]:
        p = self.current_player
        turn = self.current_turn
        darts_left_turn = 3 - (len(turn.darts) if turn else 0)
        darts_left = min(darts_left_turn, self.settings.darts_per_target - self.darts_on_target[p])
        route = (
            suggest_checkout(self.remaining[p], max(darts_left, 1), "double")
            if self.index[p] < len(self.targets)
            else None
        )
        return {
            "targets": self.targets,
            "target_index": list(self.index),
            "remaining": list(self.remaining),
            "successes": list(self.successes),
            "results": [list(r) for r in self.results],
            "darts_on_target": list(self.darts_on_target),
            "checkout": [d.label for d in route] if route else None,
        }

    def settings_dict(self) -> dict[str, Any]:
        s = self.settings
        return {
            "count": s.count,
            "min_score": s.min_score,
            "max_score": s.max_score,
            "darts_per_target": s.darts_per_target,
            "seed": s.seed,
        }


# --- Doubles training ----------------------------------------------------------------------


@dataclass(frozen=True)
class DoublesTrainingSettings:
    order: Literal["sequential", "random"] = "sequential"
    include_bull: bool = True
    seed: int = field(default_factory=lambda: random.randint(1, 1_000_000))


class DoublesTrainingGame(Game):
    mode = "doubles_training"

    def __init__(self, player_count: int, settings: DoublesTrainingSettings) -> None:
        self.settings = settings
        targets = list(NUMBERS) + ([BULL] if settings.include_bull else [])
        if settings.order == "random":
            random.Random(settings.seed).shuffle(targets)
        self.targets = targets
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.hits = [0] * self.player_count
        self.hits_by_target: list[dict[int, int]] = [{} for _ in range(self.player_count)]

    def _target(self, turn: Turn) -> int:
        index = self.turns_of(turn.player).index(turn)
        return self.targets[min(index, len(self.targets) - 1)]

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        target = self._target(turn)
        hit = dart.segment == target and dart.multiplier == 2
        turn.values.append(1 if hit else 0)
        if hit:
            p = turn.player
            self.hits[p] += 1
            self.hits_by_target[p][target] = self.hits_by_target[p].get(target, 0) + 1

    def _after_turn(self, turn: Turn) -> int | None:
        if all(len(self.turns_of(p)) >= len(self.targets) for p in range(self.player_count)):
            return _best([float(h) for h in self.hits])
        return None

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.hits[player], "hits": self.hits[player]}

    def _leg_state(self) -> dict[str, Any]:
        rounds = len(self.turns_of(self.current_player))
        if self.current_turn is not None:
            rounds -= 1
        index = min(rounds, len(self.targets) - 1)
        return {
            "targets": self.targets,
            "target": _target_label(self.targets[index], 2),
            "round": index + 1,
            "rounds": len(self.targets),
            "hits": list(self.hits),
            "hits_by_target": [{str(k): v for k, v in h.items()} for h in self.hits_by_target],
        }

    def settings_dict(self) -> dict[str, Any]:
        return {
            "order": self.settings.order,
            "include_bull": self.settings.include_bull,
            "seed": self.settings.seed,
        }


# --- Bull-off (throwing order) -------------------------------------------------------------


def bull_distance_class(dart: Dart) -> int:
    """How close a dart is to the bull, by field: 0 = bull, 1 = 25, then single inner, triple,
    single outer, double, miss."""
    if dart.segment == BULL:
        return 0 if dart.multiplier == 2 else 1
    if dart.is_miss:
        return 6
    return {1: 2, 3: 3, 2: 5}[dart.multiplier]


class BullOffGame(Game):
    """Everybody throws one dart at the bull; the closest starts. On a tie all throw again.
    (Single darts are not told apart into inner and outer single without a board position.)"""

    mode = "bull_off"

    def __init__(self, player_count: int, _settings: object = None) -> None:
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.last_round: list[int | None] = [None] * self.player_count

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        turn.values.append(bull_distance_class(dart))
        turn.stop = True  # one dart per player and round

    def _after_turn(self, turn: Turn) -> int | None:
        counts = [len(self.turns_of(p)) for p in range(self.player_count)]
        if len(set(counts)) != 1:
            return None
        # a round is complete: compare the last dart of every player
        classes = [self.turns_of(p)[-1].values[0] for p in range(self.player_count)]
        self.last_round = list(classes)
        best = min(classes)
        if classes.count(best) == 1:
            return classes.index(best)
        return None

    def player_result(self, player: int) -> dict[str, int]:
        return {}

    def _leg_state(self) -> dict[str, Any]:
        return {"last_round": list(self.last_round)}

    def settings_dict(self) -> dict[str, Any]:
        return {}
