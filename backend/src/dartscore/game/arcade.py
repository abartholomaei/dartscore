"""Arcade modes: the board is the game world. Objects sit on real board positions and a dart
hits whatever it lands on (by distance in mm), not by field.

Monster hunt: every round a few monsters sit on the board (the same set for every player of
that round, drawn from the seed). A dart takes out every monster it lands on; a dart that hits
nothing makes the remaining ones grow - easier to hit, but worth less. Wanderers move a bit
after each dart. The last round counts double. Most points win.

Darts typed in by hand have no position; the middle of their field is used instead.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Any, Literal

from dartscore.game.base import Game, GameError, MatchSettings, Turn
from dartscore.game.dart import Dart
from dartscore.game.geometry import R_DOUBLE_OUTER, field_center

Difficulty = Literal["easy", "medium", "hard"]

# monster kinds: base radius (mm), points, whether it moves along the board
KINDS: dict[str, dict[str, Any]] = {
    "blob": {"radius": 20.0, "value": 50, "wanders": False},
    "imp": {"radius": 15.0, "value": 100, "wanders": False},
    "bat": {"radius": 13.0, "value": 150, "wanders": True},
    "king": {"radius": 11.0, "value": 250, "wanders": False},
}
LEVELS: dict[str, dict[str, Any]] = {
    "easy": {"count": 4, "size": 1.25, "kinds": ["blob", "blob", "imp", "imp", "bat"]},
    "medium": {"count": 5, "size": 1.0, "kinds": ["blob", "imp", "imp", "bat", "king"]},
    "hard": {"count": 6, "size": 0.8, "kinds": ["imp", "bat", "bat", "king", "king"]},
}
GROWTH = 1.25  # radius factor after a dart that hit nothing
VALUE_LOSS = 0.8  # value factor after such a dart
WANDER_DEG = 24.0  # a wanderer moves this far around the bull after each dart


@dataclass
class Monster:
    id: int
    kind: str
    x: float
    y: float
    radius: float
    value: int
    alive: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "radius": round(self.radius, 1),
            "value": self.value,
            "alive": self.alive,
        }


@dataclass(frozen=True)
class MonsterHuntSettings:
    rounds: int = 8
    difficulty: Difficulty = "medium"
    seed: int = field(default_factory=lambda: random.randint(1, 1_000_000))

    def __post_init__(self) -> None:
        if self.rounds not in (5, 8, 10):
            raise GameError("invalid_settings", "rounds must be 5, 8 or 10")
        if self.difficulty not in LEVELS:
            raise GameError("invalid_settings", "difficulty must be easy, medium or hard")


def dart_position(dart: Dart, position: tuple[float, float] | None) -> tuple[float, float] | None:
    """Where the dart counts: the detected position, else the middle of its field."""
    return position if position is not None else field_center(dart)


class MonsterHuntGame(Game):
    mode = "monster_hunt"

    def __init__(self, player_count: int, settings: MonsterHuntSettings) -> None:
        self.settings = settings
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.scores = [0] * self.player_count
        self.kills = [0] * self.player_count
        # what the last dart did, for the animation: killed monster ids, points, grew
        self.last_effect: dict[str, Any] | None = None

    # --- the field ------------------------------------------------------------------

    def field_for(self, round_number: int) -> list[Monster]:
        """The monsters of a round, identical for every player (seeded)."""
        level = LEVELS[self.settings.difficulty]
        rng = random.Random(self.settings.seed * 1000 + round_number)
        monsters: list[Monster] = []
        attempts = 0
        while len(monsters) < level["count"] and attempts < 500:
            attempts += 1
            kind = rng.choice(level["kinds"])
            spec = KINDS[kind]
            radius = spec["radius"] * level["size"]
            r = rng.uniform(25.0, R_DOUBLE_OUTER - radius)
            angle = rng.uniform(0, 2 * math.pi)
            x, y = r * math.cos(angle), r * math.sin(angle)
            # keep the monsters apart so each one is its own target
            if any(math.hypot(x - m.x, y - m.y) < radius + m.radius + 6 for m in monsters):
                continue
            monsters.append(Monster(len(monsters), kind, x, y, radius, spec["value"]))
        return monsters

    def _round_of(self, turn: Turn) -> int:
        return self.turns_of(turn.player).index(turn) + 1

    def _multiplier(self, round_number: int) -> int:
        return 2 if round_number == self.settings.rounds else 1

    def field_after(self, turn: Turn) -> list[Monster]:
        """The round's monsters after the darts thrown so far in ``turn``."""
        monsters = self.field_for(self._round_of(turn))
        for dart, position in zip(turn.darts, turn.positions, strict=False):
            self._apply_dart(monsters, dart, position)
        return monsters

    @staticmethod
    def _apply_dart(
        monsters: list[Monster], dart: Dart, position: tuple[float, float] | None
    ) -> tuple[list[Monster], bool]:
        """Kills what the dart hits (returns them) or lets the survivors grow; wanderers move."""
        at = dart_position(dart, position)
        killed = [
            m
            for m in monsters
            if m.alive and at is not None and math.hypot(at[0] - m.x, at[1] - m.y) <= m.radius
        ]
        for m in killed:
            m.alive = False
        grew = not killed
        for m in monsters:
            if not m.alive:
                continue
            if grew:
                m.radius *= GROWTH
                m.value = max(10, int(round(m.value * VALUE_LOSS / 5) * 5))
            if KINDS[m.kind]["wanders"]:
                r = math.hypot(m.x, m.y)
                angle = math.atan2(m.y, m.x) - math.radians(WANDER_DEG)
                m.x, m.y = r * math.cos(angle), r * math.sin(angle)
        return killed, grew

    # --- game rules -----------------------------------------------------------------

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        round_number = self._round_of(turn)
        monsters = self.field_for(round_number)
        for d, pos in zip(turn.darts[:-1], turn.positions[:-1], strict=False):
            self._apply_dart(monsters, d, pos)
        before = {m.id: m.value for m in monsters if m.alive}
        killed, grew = self._apply_dart(monsters, dart, turn.positions[-1])
        points = sum(before[m.id] for m in killed) * self._multiplier(round_number)
        turn.values.append(points)
        self.scores[p] += points
        self.kills[p] += len(killed)
        self.last_effect = {
            "player": p,
            "killed": [m.id for m in killed],
            "points": points,
            "grew": grew,
            "position": dart_position(dart, turn.positions[-1]),
        }
        if not any(m.alive for m in monsters):
            turn.stop = True  # all monsters gone: the turn is over

    def _after_turn(self, turn: Turn) -> int | None:
        rounds = self.settings.rounds
        if all(len(self.turns_of(p)) >= rounds for p in range(self.player_count)):
            best = max(self.scores)
            return self.scores.index(best)
        return None

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.scores[player], "hits": self.kills[player]}

    def _leg_state(self) -> dict[str, Any]:
        p = self.current_player
        turn = self.current_turn
        if turn is not None and turn.player == p:
            round_number = self._round_of(turn)
            monsters = self.field_after(turn)
            darts = [
                {"label": d.label, "position": dart_position(d, pos)}
                for d, pos in zip(turn.darts, turn.positions, strict=False)
            ]
        else:
            round_number = min(len(self.turns_of(p)) + 1, self.settings.rounds)
            monsters = self.field_for(round_number)
            darts = []
        return {
            "scores": list(self.scores),
            "kills": list(self.kills),
            "round": round_number,
            "rounds": self.settings.rounds,
            "double_round": round_number == self.settings.rounds,
            "monsters": [m.to_dict() for m in monsters],
            "arcade_darts": darts,
            "last_effect": self.last_effect,
        }

    def settings_dict(self) -> dict[str, Any]:
        s = self.settings
        return {"rounds": s.rounds, "difficulty": s.difficulty, "seed": s.seed}
