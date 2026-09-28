"""Arcade modes: the board is the game world. Objects sit on real board positions and a dart
hits whatever it lands on (by distance in mm), not by field.

Monster hunt (after Scolia's Zombie Shooter): one monster at a time stands on the board. Every
round has its own line-up of monsters (the same for every player of that round, drawn from the
seed). A dart close to the monster's middle takes it out at once (a "headshot"); a dart that
only grazes it costs it one life, so a sloppy thrower needs two or three hits. A caught monster
makes room for the next one of the line-up. A dart that hits nothing makes the monster grow -
easier to hit, but worth less. Walkers step along the board after every dart and are worth
more. The last round counts double. Most points win.

Melon samurai: every turn a fresh fruit covers the board. A dart is a sword cut straight
through where it landed, across the line to the bull; the piece on the dart's side flies off
and scores by its size (a whole fruit is worth 1000). The closer to the bull, the bigger the
piece. A dart where no fruit is left (thrown past the bull) cuts only air. The bullseye cuts
away everything that is left. The last round is a big watermelon and counts double. Most points win.

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


# --- Melon samurai ---------------------------------------------------------------------------

Point = tuple[float, float]
FRUITS = ("orange", "kiwi", "dragonfruit", "lime")
FINALE = "watermelon"  # the last round, worth double
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
            return FINALE
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
