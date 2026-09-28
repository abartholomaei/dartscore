"""Arcade modes: the board is the game world. Objects sit on real board positions and a dart
hits whatever it lands on (by distance in mm), not by field.

Monster hunt (after Scolia's Zombie Shooter): one monster at a time stands on the board. Every
round has its own line-up of monsters (the same for every player of that round, drawn from the
seed). A dart close to the monster's middle takes it out at once (a "headshot"); a dart that
only grazes it costs it one life, so a sloppy thrower needs two or three hits. A caught monster
makes room for the next one of the line-up. A dart that hits nothing makes the monster grow -
easier to hit, but worth less. Walkers step along the board after every dart and are worth
more. The last round counts double. Most points win.

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

# monster kinds: base radius (mm), points, lives, whether it walks along the board
KINDS: dict[str, dict[str, Any]] = {
    "blob": {"radius": 26.0, "value": 50, "hp": 2, "walks": False},
    "imp": {"radius": 22.0, "value": 75, "hp": 2, "walks": False},
    "bat": {"radius": 19.0, "value": 120, "hp": 1, "walks": True},
    "king": {"radius": 21.0, "value": 150, "hp": 3, "walks": False},
}
# size: radius factor, headshot: share of the radius that counts as a headshot
LEVELS: dict[str, dict[str, Any]] = {
    "easy": {"size": 1.3, "headshot": 0.45, "kinds": ["blob", "blob", "imp", "bat"]},
    "medium": {"size": 1.0, "headshot": 0.35, "kinds": ["blob", "imp", "imp", "bat", "king"]},
    "hard": {"size": 0.8, "headshot": 0.3, "kinds": ["imp", "bat", "bat", "king"]},
}
LINE_UP = 3  # monsters per round: one turn has three darts, so three is always enough
GROWTH = 1.2  # radius factor after a dart that hit nothing
VALUE_LOSS = 0.8  # value factor after such a dart
HEADSHOT_BONUS = 1.5  # points factor for a monster taken out by a headshot
WALK_DEG = 28.0  # a walker moves this far around the bull after each dart


@dataclass
class Monster:
    id: int
    kind: str
    x: float
    y: float
    radius: float
    value: int
    hp: int
    max_hp: int
    # waiting (not on the board yet), active (the one to shoot) or dead
    status: str = "waiting"

    @property
    def alive(self) -> bool:
        return self.status != "dead"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "radius": round(self.radius, 1),
            "value": self.value,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "status": self.status,
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
        # what the last dart did, for the animation
        self.last_effect: dict[str, Any] | None = None

    # --- the field ------------------------------------------------------------------

    def field_for(self, round_number: int) -> list[Monster]:
        """The line-up of a round, identical for every player (seeded); the first one is up."""
        level = LEVELS[self.settings.difficulty]
        rng = random.Random(self.settings.seed * 1000 + round_number)
        monsters: list[Monster] = []
        attempts = 0
        while len(monsters) < LINE_UP:
            attempts += 1
            kind = rng.choice(level["kinds"])
            spec = KINDS[kind]
            radius = spec["radius"] * level["size"]
            r = rng.uniform(30.0, R_DOUBLE_OUTER - radius - 4)
            angle = rng.uniform(0, 2 * math.pi)
            x, y = r * math.cos(angle), r * math.sin(angle)
            # the next monster shows up somewhere else than the one before
            last = monsters[-1] if monsters else None
            if last and math.hypot(x - last.x, y - last.y) < 70 and attempts < 200:
                continue
            monsters.append(
                Monster(len(monsters), kind, x, y, radius, spec["value"], spec["hp"], spec["hp"])
            )
        monsters[0].status = "active"
        return monsters

    def _round_of(self, turn: Turn) -> int:
        return self.turns_of(turn.player).index(turn) + 1

    def _multiplier(self, round_number: int) -> int:
        return 2 if round_number == self.settings.rounds else 1

    def field_after(self, turn: Turn) -> list[Monster]:
        """The round's line-up after the darts thrown so far in ``turn``."""
        monsters = self.field_for(self._round_of(turn))
        for dart, position in zip(turn.darts, turn.positions, strict=False):
            self._apply_dart(monsters, dart, position)
        return monsters

    def _apply_dart(
        self, monsters: list[Monster], dart: Dart, position: tuple[float, float] | None
    ) -> dict[str, Any]:
        """Shoots the active monster; returns what happened (hit, killed, headshot, grew)."""
        at = dart_position(dart, position)
        target = next((m for m in monsters if m.status == "active"), None)
        result: dict[str, Any] = {
            "target": None, "hit": False, "killed": False, "headshot": False, "grew": False,
            "value": 0,
        }  # fmt: skip
        if target is None:
            return result
        result["target"] = target.id
        result["value"] = target.value
        distance = math.hypot(at[0] - target.x, at[1] - target.y) if at is not None else math.inf
        if distance <= target.radius:
            result["hit"] = True
            if distance <= target.radius * LEVELS[self.settings.difficulty]["headshot"]:
                result["headshot"] = True
                target.hp = 0
            else:
                target.hp -= 1
            if target.hp <= 0:
                result["killed"] = True
                target.status = "dead"
                following = next((m for m in monsters if m.status == "waiting"), None)
                if following is not None:
                    following.status = "active"
                return result
        else:
            result["grew"] = True
            target.radius *= GROWTH
            target.value = max(10, int(round(target.value * VALUE_LOSS / 5) * 5))
        if KINDS[target.kind]["walks"]:
            r = math.hypot(target.x, target.y)
            angle = math.atan2(target.y, target.x) - math.radians(WALK_DEG)
            target.x, target.y = r * math.cos(angle), r * math.sin(angle)
        return result

    # --- game rules -----------------------------------------------------------------

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        round_number = self._round_of(turn)
        monsters = self.field_for(round_number)
        for d, pos in zip(turn.darts[:-1], turn.positions[:-1], strict=False):
            self._apply_dart(monsters, d, pos)
        result = self._apply_dart(monsters, dart, turn.positions[-1])
        points = 0
        if result["killed"]:
            bonus = HEADSHOT_BONUS if result["headshot"] else 1
            points = int(round(result["value"] * bonus / 5) * 5) * self._multiplier(round_number)
            self.kills[p] += 1
        turn.values.append(points)
        self.scores[p] += points
        self.last_effect = {
            "player": p,
            "target": result["target"],
            "hit": result["hit"],
            "killed": result["killed"],
            "headshot": result["headshot"],
            "grew": result["grew"],
            "points": points,
            "position": dart_position(dart, turn.positions[-1]),
        }
        if not any(m.alive for m in monsters):
            turn.stop = True  # the whole line-up is gone: the turn is over

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
        turns = self.legs[-1].turns
        if turn is None and self._awaiting_next and turns:
            turn = turns[-1]  # the finished turn stays on screen until the darts are pulled
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
