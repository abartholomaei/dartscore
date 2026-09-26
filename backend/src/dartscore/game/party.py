"""Party and practice modes: Killer, Halve-It, Gotcha and score training."""

import random
from dataclasses import dataclass, field
from typing import Any

from dartscore.game.base import Game, GameError, MatchSettings, Turn
from dartscore.game.dart import BULL, Dart
from dartscore.game.training import _best

# --- Killer --------------------------------------------------------------------------------


@dataclass(frozen=True)
class KillerSettings:
    lives: int = 3
    # hits on the own double needed to become a killer
    hits_to_arm: int = 1
    seed: int = field(default_factory=lambda: random.randint(1, 1_000_000))

    def __post_init__(self) -> None:
        if not 1 <= self.lives <= 9 or not 1 <= self.hits_to_arm <= 3:
            raise GameError("invalid_settings", "lives 1-9, hits_to_arm 1-3")


class KillerGame(Game):
    """Every player has a number. Hit its double to become a killer; killers take lives with the
    doubles of the others' numbers (a double of your own number costs you a life). The last one
    with lives left wins."""

    mode = "killer"
    min_players = 2

    def __init__(self, player_count: int, settings: KillerSettings) -> None:
        self.settings = settings
        self.numbers = random.Random(settings.seed).sample(range(1, 21), player_count)
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.lives = [self.settings.lives] * self.player_count
        self.armed = [0] * self.player_count
        self._last_standing: int | None = None

    def _alive(self) -> list[int]:
        return [p for p in range(self.player_count) if self.lives[p] > 0]

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        value = 0
        if dart.is_double and dart.segment in self.numbers:
            owner = self.numbers.index(dart.segment)
            if owner == p:
                if self.armed[p] < self.settings.hits_to_arm:
                    self.armed[p] += 1
                    value = 1
                elif self.lives[p] > 0:
                    self.lives[p] -= 1  # killers must not hit their own double
            elif self.armed[p] >= self.settings.hits_to_arm and self.lives[owner] > 0:
                self.lives[owner] -= 1
                value = 1
        turn.values.append(value)
        alive = self._alive()
        if len(alive) == 1:
            turn.checkout = alive[0] == p
            if not turn.checkout:
                turn.stop = True
                self._last_standing = alive[0]
        elif self.lives[p] == 0:
            turn.stop = True  # killed themselves

    def _after_turn(self, turn: Turn) -> int | None:
        return self._last_standing

    def _next_player(self, player: int) -> int:
        for step in range(1, self.player_count + 1):
            candidate = (player + step) % self.player_count
            if self.lives[candidate] > 0:
                return candidate
        return player

    def player_result(self, player: int) -> dict[str, int]:
        hits = sum(1 for t in self.turns_of(player, self.legs[0]) for v in t.values if v)
        return {"score": self.lives[player], "hits": hits}

    def _leg_state(self) -> dict[str, Any]:
        return {
            "numbers": list(self.numbers),
            "lives": list(self.lives),
            "killer": [a >= self.settings.hits_to_arm for a in self.armed],
        }

    def settings_dict(self) -> dict[str, Any]:
        s = self.settings
        return {"lives": s.lives, "hits_to_arm": s.hits_to_arm, "seed": s.seed}


# --- Halve-It ------------------------------------------------------------------------------

# a target is a number (any ring), "D"/"T" (any double/triple) or 25 (bull, both rings)
HALVE_IT_TARGETS: tuple[int | str, ...] = (20, 16, "D", 17, 18, "T", 19, BULL)


@dataclass(frozen=True)
class HalveItSettings:
    start: int = 40


class HalveItGame(Game):
    """Round by round a fixed target; hits score their points. A round without a hit on the
    target halves the score."""

    mode = "halve_it"

    def __init__(self, player_count: int, settings: HalveItSettings) -> None:
        self.settings = settings
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.scores = [self.settings.start] * self.player_count
        self.hits = [0] * self.player_count

    def _target(self, turn: Turn) -> int | str:
        index = self.turns_of(turn.player).index(turn)
        return HALVE_IT_TARGETS[min(index, len(HALVE_IT_TARGETS) - 1)]

    @staticmethod
    def _hits(target: int | str, dart: Dart) -> bool:
        if target == "D":
            return dart.is_double
        if target == "T":
            return dart.is_triple
        return dart.segment == target

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        value = dart.points if self._hits(self._target(turn), dart) else 0
        turn.values.append(value)
        if value:
            self.scores[turn.player] += value
            self.hits[turn.player] += 1

    def _after_turn(self, turn: Turn) -> int | None:
        if not any(turn.values):
            self.scores[turn.player] //= 2
        if all(len(self.turns_of(p)) >= len(HALVE_IT_TARGETS) for p in range(self.player_count)):
            return _best([float(s) for s in self.scores])
        return None

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.scores[player], "hits": self.hits[player]}

    def _leg_state(self) -> dict[str, Any]:
        rounds = len(self.turns_of(self.current_player))
        if self.current_turn is not None:
            rounds -= 1
        index = min(rounds, len(HALVE_IT_TARGETS) - 1)
        target = HALVE_IT_TARGETS[index]
        return {
            "scores": list(self.scores),
            "target": {"D": "D", "T": "T", BULL: "BULL"}.get(target, str(target)),
            "round": index + 1,
            "rounds": len(HALVE_IT_TARGETS),
        }

    def settings_dict(self) -> dict[str, Any]:
        return {"start": self.settings.start}


# --- Gotcha --------------------------------------------------------------------------------


@dataclass(frozen=True)
class GotchaSettings:
    target: int = 301

    def __post_init__(self) -> None:
        if self.target not in (101, 201, 301, 501):
            raise GameError("invalid_settings", "target must be 101, 201, 301 or 501")


class GotchaGame(Game):
    """Count up to exactly the target. Landing on an opponent's score sends them back to zero;
    going over busts the turn."""

    mode = "gotcha"
    min_players = 2

    def __init__(self, player_count: int, settings: GotchaSettings) -> None:
        self.settings = settings
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.scores = [0] * self.player_count

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        new = self.scores[p] + dart.points
        turn.values.append(dart.points)
        if new > self.settings.target:
            turn.bust = True
            self.scores[p] -= sum(turn.values[:-1])
            return
        self.scores[p] = new
        if new == self.settings.target:
            turn.checkout = True
            return
        for q in range(self.player_count):
            if q != p and dart.points and self.scores[q] == new:
                self.scores[q] = 0  # gotcha

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.scores[player], "hits": 0}

    def _leg_state(self) -> dict[str, Any]:
        return {"scores": list(self.scores), "goal": self.settings.target}

    def settings_dict(self) -> dict[str, Any]:
        return {"target": self.settings.target}


# --- Score training ------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreTrainingSettings:
    rounds: int = 10

    def __post_init__(self) -> None:
        if self.rounds not in (5, 10, 20, 33):
            raise GameError("invalid_settings", "rounds must be 5, 10, 20 or 33")


class ScoreTrainingGame(Game):
    """Score as much as possible in a fixed number of turns (3-dart average practice)."""

    mode = "score_training"

    def __init__(self, player_count: int, settings: ScoreTrainingSettings) -> None:
        self.settings = settings
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.scores = [0] * self.player_count

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        turn.values.append(dart.points)
        self.scores[turn.player] += dart.points

    def _after_turn(self, turn: Turn) -> int | None:
        if all(len(self.turns_of(p)) >= self.settings.rounds for p in range(self.player_count)):
            return _best([float(s) for s in self.scores])
        return None

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.scores[player], "hits": 0}

    def _leg_state(self) -> dict[str, Any]:
        rounds = len(self.turns_of(self.current_player))
        if self.current_turn is not None:
            rounds -= 1
        return {
            "scores": list(self.scores),
            "round": min(rounds + 1, self.settings.rounds),
            "rounds": self.settings.rounds,
        }

    def settings_dict(self) -> dict[str, Any]:
        return {"rounds": self.settings.rounds}
