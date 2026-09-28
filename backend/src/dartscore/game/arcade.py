"""Arcade modes: the board is the game world. Objects sit on real board positions and a dart
hits whatever it lands on (by distance in mm), not by field.

Monster hunt: every round a few monsters sit on the board (the same set for every player of
that round, drawn from the seed). A dart takes out every monster it lands on; a dart that hits
nothing makes the remaining ones grow - easier to hit, but worth less. Wanderers move a bit
after each dart. The last round counts double. Most points win.

Melon samurai: every turn a fresh fruit covers the board. A dart is a sword cut straight
through where it landed, across the line to the bull; the piece on the dart's side flies off
and scores by its size (a whole fruit is worth 1000). The closer to the bull, the bigger the
piece. A dart where no fruit is left (thrown past the bull) cuts only air. The bullseye cuts
away everything that is left. The last round counts double. Most points win.

Darts typed in by hand have no position; the middle of their field is used instead.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Any, Literal

from dartscore.game.base import Game, GameError, MatchSettings, Turn
from dartscore.game.dart import Dart
from dartscore.game.geometry import R_BULL, R_DOUBLE_OUTER, field_center

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


def shown_turn(game: Game) -> Turn | None:
    """The turn whose board is on screen: the running one, or the one just completed until
    the darts are pulled (and the last one when the game is over)."""
    leg = game.legs[-1]
    if not leg.turns:
        return None
    turn = leg.turns[-1]
    if turn.player != game.current_player:
        return None
    if turn.closed and not (game.turn_complete or game.finished):
        return None
    return turn


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
        turn = shown_turn(self)
        if turn is not None:
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


# --- Melon samurai ---------------------------------------------------------------------------

Point = tuple[float, float]
FRUITS = ("watermelon", "orange", "kiwi", "dragonfruit", "lime")
FRUIT_POINTS = 1000  # a whole fruit
FRUIT_EDGES = 96  # the round fruit as a polygon


def _fruit_outline() -> list[Point]:
    """The whole fruit: a circle over the board, counter-clockwise."""
    step = 2 * math.pi / FRUIT_EDGES
    return [
        (R_DOUBLE_OUTER * math.cos(i * step), R_DOUBLE_OUTER * math.sin(i * step))
        for i in range(FRUIT_EDGES)
    ]


def polygon_area(polygon: list[Point]) -> float:
    """Shoelace formula."""
    edges = zip(polygon, polygon[1:] + polygon[:1], strict=True)
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in edges)) / 2


def split_polygon(
    polygon: list[Point], normal: Point, offset: float
) -> tuple[list[Point], list[Point]]:
    """Cuts a convex polygon along the line ``p · normal = offset``; returns the part with
    ``p · normal <= offset`` and the part beyond it."""
    keep: list[Point] = []
    cut: list[Point] = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        da = a[0] * normal[0] + a[1] * normal[1] - offset
        db = b[0] * normal[0] + b[1] * normal[1] - offset
        (keep if da <= 0 else cut).append(a)
        if (da < 0 < db) or (db < 0 < da):
            t = da / (da - db)
            crossing = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            keep.append(crossing)
            cut.append(crossing)
    return keep, cut


def inside_polygon(polygon: list[Point], point: Point) -> bool:
    """Whether ``point`` lies in a convex, counter-clockwise polygon."""
    if len(polygon) < 3:
        return False
    return all(
        (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]) >= -1e-9
        for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True)
    )


WHOLE_FRUIT = polygon_area(_fruit_outline())


@dataclass(frozen=True)
class Slice:
    """What one dart did to the fruit."""

    result: Literal["slice", "perfect", "air"]
    fraction: float  # share of the whole fruit cut off
    piece: list[Point]  # the part that flies off
    rest: list[Point]  # what is left of the fruit
    cut: tuple[Point, Point] | None  # the sword line across the fruit


def slice_fruit(fruit: list[Point], at: Point | None) -> Slice:
    """Cuts the fruit with a dart at ``at`` (mm, see the module docs)."""
    if at is None or not inside_polygon(fruit, at):
        return Slice("air", 0.0, [], fruit, None)
    distance = math.hypot(*at)
    if distance <= R_BULL:
        return Slice("perfect", polygon_area(fruit) / WHOLE_FRUIT, fruit, [], None)
    normal = (at[0] / distance, at[1] / distance)
    rest, piece = split_polygon(fruit, normal, distance)
    half = math.sqrt(max(R_DOUBLE_OUTER**2 - distance**2, 0.0))
    along = (-normal[1], normal[0])
    cut = (
        (at[0] - along[0] * half, at[1] - along[1] * half),
        (at[0] + along[0] * half, at[1] + along[1] * half),
    )
    return Slice("slice", polygon_area(piece) / WHOLE_FRUIT, piece, rest, cut)


def _rounded(polygon: list[Point]) -> list[list[float]]:
    return [[round(x, 1), round(y, 1)] for x, y in polygon]


@dataclass(frozen=True)
class MelonSamuraiSettings:
    rounds: int = 5

    def __post_init__(self) -> None:
        if self.rounds not in (5, 8, 10):
            raise GameError("invalid_settings", "rounds must be 5, 8 or 10")


class MelonSamuraiGame(Game):
    mode = "melon_samurai"

    def __init__(self, player_count: int, settings: MelonSamuraiSettings) -> None:
        self.settings = settings
        super().__init__(player_count, MatchSettings())

    def _start_leg(self) -> None:
        self.scores = [0] * self.player_count
        self.slices = [0] * self.player_count
        # what the last dart did, for the animation
        self.last_effect: dict[str, Any] | None = None

    def _round_of(self, turn: Turn) -> int:
        return self.turns_of(turn.player).index(turn) + 1

    def fruit_of(self, round_number: int) -> str:
        if round_number == self.settings.rounds:
            return "golden"
        return FRUITS[(round_number - 1) % len(FRUITS)]

    def _multiplier(self, round_number: int) -> int:
        return 2 if round_number == self.settings.rounds else 1

    def fruit_after(self, darts: list[Dart], positions: list[Point | None]) -> list[Point]:
        fruit = _fruit_outline()
        for dart, position in zip(darts, positions, strict=False):
            fruit = slice_fruit(fruit, dart_position(dart, position)).rest
        return fruit

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        round_number = self._round_of(turn)
        fruit = self.fruit_after(turn.darts[:-1], turn.positions[:-1])
        at = dart_position(dart, turn.positions[-1])
        result = slice_fruit(fruit, at)
        points = round(result.fraction * FRUIT_POINTS) * self._multiplier(round_number)
        turn.values.append(points)
        self.scores[p] += points
        if result.result != "air":
            self.slices[p] += 1
        self.last_effect = {
            "player": p,
            "result": result.result,
            "points": points,
            "piece": _rounded(result.piece),
            "cut": [list(c) for c in result.cut] if result.cut else None,
            "position": at,
        }
        if not result.rest:
            turn.stop = True  # nothing left to cut

    def _after_turn(self, turn: Turn) -> int | None:
        rounds = self.settings.rounds
        if all(len(self.turns_of(p)) >= rounds for p in range(self.player_count)):
            return self.scores.index(max(self.scores))
        return None

    def player_result(self, player: int) -> dict[str, int]:
        return {"score": self.scores[player], "hits": self.slices[player]}

    def _leg_state(self) -> dict[str, Any]:
        p = self.current_player
        turn = shown_turn(self)
        if turn is not None:
            round_number = self._round_of(turn)
            fruit = self.fruit_after(turn.darts, turn.positions)
            darts = [
                {"label": d.label, "position": dart_position(d, pos)}
                for d, pos in zip(turn.darts, turn.positions, strict=False)
            ]
        else:
            round_number = min(len(self.turns_of(p)) + 1, self.settings.rounds)
            fruit = _fruit_outline()
            darts = []
        return {
            "scores": list(self.scores),
            "hits": list(self.slices),
            "round": round_number,
            "rounds": self.settings.rounds,
            "double_round": round_number == self.settings.rounds,
            "fruit": self.fruit_of(round_number),
            "fruit_left": _rounded(fruit),
            "fruit_share": round(polygon_area(fruit) / WHOLE_FRUIT, 3),
            "arcade_darts": darts,
            "last_effect": self.last_effect,
        }

    def settings_dict(self) -> dict[str, Any]:
        return {"rounds": self.settings.rounds}
