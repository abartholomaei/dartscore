"""Computer opponent: picks a target like a sensible player and throws with a normal scatter.

The skill level is the bot's expected 3-dart average when it aims at the treble 20; it is turned
into the standard deviation of the throws (in mm on the board) with a simulated table.
"""

import itertools
import math
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass

import structlog

from dartscore.game import Dart, GameError
from dartscore.game.base import Game
from dartscore.game.checkout import suggest_checkout
from dartscore.game.cricket import TARGETS as CRICKET_TARGETS
from dartscore.game.cricket import CricketGame
from dartscore.game.dart import BULL
from dartscore.game.x01 import X01Game
from dartscore.services.games import GameService
from dartscore.vision.board import (
    R_DOUBLE_INNER,
    R_DOUBLE_OUTER,
    R_TRIPLE_INNER,
    R_TRIPLE_OUTER,
    SEGMENT_ANGLE_DEG,
    SEGMENTS,
    score_at,
)

log = structlog.get_logger(__name__)

# (scatter sigma in mm, 3-dart average aiming at T20), simulated with 40000 darts each
_SKILL_TABLE = (
    (5.0, 129.4), (8.0, 101.4), (10.0, 88.5), (13.0, 72.8), (16.0, 61.7), (20.0, 52.0),
    (25.0, 44.6), (30.0, 41.1), (35.0, 38.4), (40.0, 36.6), (50.0, 33.5), (60.0, 30.7),
    (70.0, 28.1),
)  # fmt: skip

# the leaves a player sets up with a single when there is no checkout
_GOOD_DOUBLES = (40, 32, 36, 24, 16, 20, 8, 12, 4, 2)

DART_DELAY = 1.3  # seconds between the bot's darts
PULL_DELAY = 2.5  # seconds after the last dart before the next player is up


def sigma_for_average(average: float) -> float:
    """Scatter (mm) that gives roughly this 3-dart average (interpolated, clamped)."""
    table = sorted(_SKILL_TABLE, key=lambda row: row[1])
    if average <= table[0][1]:
        return table[0][0]
    for (s0, a0), (s1, a1) in itertools.pairwise(table):
        if average <= a1:
            return s0 + (s1 - s0) * (average - a0) / (a1 - a0)
    return table[-1][0]


def aim_point(dart: Dart) -> tuple[float, float]:
    """The middle of the target field in board mm (x right, y up)."""
    if dart.segment == BULL:
        return 0.0, 0.0
    angle = math.radians(90.0 - SEGMENTS.index(dart.segment) * SEGMENT_ANGLE_DEG)
    if dart.multiplier == 3:
        r = (R_TRIPLE_INNER + R_TRIPLE_OUTER) / 2
    elif dart.multiplier == 2:
        r = (R_DOUBLE_INNER + R_DOUBLE_OUTER) / 2
    else:
        r = (R_TRIPLE_OUTER + R_DOUBLE_INNER) / 2  # the big outer single
    return r * math.cos(angle), r * math.sin(angle)


@dataclass(frozen=True)
class BotProfile:
    """How a bot throws: scatter (mm) and systematic offset (radial = towards the board edge,
    sideways = clockwise, mm), separately for doubles where a personal bot has data."""

    sigma: float
    bias: tuple[float, float] = (0.0, 0.0)
    double_sigma: float | None = None
    double_bias: tuple[float, float] = (0.0, 0.0)

    def for_target(self, target: Dart) -> tuple[float, tuple[float, float]]:
        if target.multiplier == 2 and self.double_sigma is not None:
            return self.double_sigma, self.double_bias
        return self.sigma, self.bias


def offset_xy(target: Dart, radial: float, sideways: float) -> tuple[float, float]:
    """Converts an offset relative to the target field into board x/y (mm)."""
    if target.segment == BULL:
        return sideways, radial
    x0, y0 = aim_point(target)
    angle = math.atan2(y0, x0)
    return (
        radial * math.cos(angle) + sideways * math.sin(angle),
        radial * math.sin(angle) - sideways * math.cos(angle),
    )


def throw_at(
    target: Dart, sigma: float, rng: random.Random, bias: tuple[float, float] = (0.0, 0.0)
) -> tuple[Dart, float, float]:
    x0, y0 = aim_point(target)
    bx, by = offset_xy(target, *bias)
    x, y = rng.gauss(x0 + bx, sigma), rng.gauss(y0 + by, sigma)
    score = score_at(x, y)
    return Dart(score.segment, score.multiplier), x, y


def _x01_target(game: X01Game, player: int) -> Dart:
    if not game.opened[player]:
        return Dart(20, 2) if game.settings.in_rule == "double" else Dart(20, 3)
    remaining = game.remaining[player]
    turn = game.current_turn
    darts_left = 3 - (len(turn.darts) if turn else 0)
    route = suggest_checkout(remaining, darts_left, game.settings.out_rule)
    if route:
        return route[0]
    if remaining > 60 or game.settings.out_rule == "single":
        return Dart(20, 3)
    # no finish this turn: leave a good double with a single
    for leave in _GOOD_DOUBLES:
        if 1 <= remaining - leave <= 20:
            return Dart(remaining - leave, 1)
    return Dart(20, 1)


def _cricket_target(game: CricketGame, player: int) -> Dart:
    marks = game.marks
    others = [q for q in range(game.player_count) if q != player]
    open_for_others = [t for t in CRICKET_TARGETS if any(marks[q][t] < 3 for q in others)]
    # close what the others could still score on, highest first; then score where they are open
    for target in CRICKET_TARGETS:
        if marks[player][target] < 3 and target in open_for_others:
            return _cricket_dart(target)
    if game.settings.variant != "no_score" and open_for_others:
        return _cricket_dart(open_for_others[0])
    for target in CRICKET_TARGETS:
        if marks[player][target] < 3:
            return _cricket_dart(target)
    return Dart(BULL, 2)


def _cricket_dart(target: int) -> Dart:
    return Dart(BULL, 2) if target == BULL else Dart(target, 3)


def choose_target(game: Game) -> Dart:
    player = game.current_player
    if isinstance(game, X01Game):
        return _x01_target(game, player)
    if isinstance(game, CricketGame):
        return _cricket_target(game, player)
    return Dart(20, 3)


class BotService:
    """Plays the bots' turns: throws their darts one by one, then passes on."""

    def __init__(
        self,
        games: GameService,
        seed: int | None = None,
        profile_source: Callable[[int, int], BotProfile] | None = None,
    ) -> None:
        self._games = games
        # builds the profile of a personal bot from the imitated player's darts
        self._profile_source = profile_source
        self._profiles: dict[tuple[int, int], BotProfile] = {}
        self._rng = random.Random(seed)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        games.add_listener(lambda _event: self._wake.set())

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="bot", daemon=True)
        self._thread.start()
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=5)
            self._wake.clear()
            try:
                while not self._stop.is_set() and self.step(DART_DELAY, PULL_DELAY):
                    pass
            except Exception:
                log.exception("bot_failed")

    def step(self, dart_delay: float = 0.0, pull_delay: float = 0.0) -> bool:
        """One bot action (after its delay). False when no bot is in control."""
        turn = self._games.bot_turn()
        if turn is None:
            return False
        game_id, game, level, bot_of = turn
        state = game.state()
        pull = state["awaiting_next"] or state["leg_winner"] is not None
        events = len(game.events)
        delay = pull_delay if pull else dart_delay
        if delay and self._stop.wait(delay):
            return False
        # a player may have entered or undone something in the meantime
        again = self._games.bot_turn()
        if again is None or again[0] != game_id or len(again[1].events) != events:
            return True
        try:
            if pull:
                self._games.next_turn(source="bot")
            else:
                target = choose_target(game)
                sigma, bias = self._profile(game_id, level, bot_of).for_target(target)
                dart, x, y = throw_at(target, sigma, self._rng, bias)
                self._games.throw(dart, source="bot", x_mm=x, y_mm=y)
        except GameError as exc:
            log.warning("bot_move_rejected", code=exc.code)
            return False
        return True

    def _profile(self, game_id: int, level: int, bot_of: int | None) -> BotProfile:
        if bot_of is None or self._profile_source is None:
            return BotProfile(sigma_for_average(level))
        key = (game_id, bot_of)
        if key not in self._profiles:
            try:
                self._profiles[key] = self._profile_source(bot_of, level)
            except Exception:
                log.exception("bot_profile_failed", player=bot_of)
                self._profiles[key] = BotProfile(sigma_for_average(level))
        return self._profiles[key]
