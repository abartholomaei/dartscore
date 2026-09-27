"""Per-player statistics of a game, derived from its legs and turns."""

from dataclasses import asdict, dataclass, field
from typing import Any

from dartscore.game.base import Game, Leg
from dartscore.game.checkout import one_dart_finish
from dartscore.game.cricket import CricketGame
from dartscore.game.x01 import X01Game

FIRST_NINE_TURNS = 3


@dataclass
class PlayerGameStats:
    darts: int = 0
    turns: int = 0
    legs_played: int = 0
    legs_won: int = 0
    won: bool = False
    # X01
    points: int = 0
    first9_points: int = 0
    first9_darts: int = 0
    checkout_attempts: int = 0
    checkouts: int = 0
    highest_finish: int = 0
    highest_turn: int = 0
    best_leg_darts: int | None = None
    darts_in_won_legs: int = 0
    busts: int = 0
    tons: dict[str, int] = field(default_factory=lambda: {"60": 0, "100": 0, "140": 0, "180": 0})
    # Cricket
    marks: int = 0
    # training modes: the mode's own score (e.g. Shanghai points, successful checkouts) and hits
    score: int | None = None
    hits: int = 0

    @property
    def average(self) -> float | None:
        """3-dart average (X01)."""
        return round(self.points / self.darts * 3, 2) if self.darts else None

    @property
    def first9_average(self) -> float | None:
        return round(self.first9_points / self.first9_darts * 3, 2) if self.first9_darts else None

    @property
    def checkout_rate(self) -> float | None:
        return round(self.checkouts / self.checkout_attempts, 4) if self.checkout_attempts else None

    @property
    def hit_rate(self) -> float | None:
        return round(self.hits / self.darts, 4) if self.darts and self.score is not None else None

    @property
    def mpr(self) -> float | None:
        """Marks per round (Cricket), a round being three darts."""
        return round(self.marks / self.darts * 3, 2) if self.darts else None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            average=self.average,
            first9_average=self.first9_average,
            checkout_rate=self.checkout_rate,
            mpr=self.mpr,
            hit_rate=self.hit_rate,
        )
        return data


def _ton_bucket(total: int) -> str | None:
    if total == 180:
        return "180"
    if total >= 140:
        return "140"
    if total >= 100:
        return "100"
    if total >= 60:
        return "60"
    return None


def _x01_leg(game: X01Game, leg: Leg, stats: list[PlayerGameStats]) -> None:
    remaining = [game.settings.start_for(p) for p in range(game.player_count)]
    opened = [game.settings.in_rule == "single"] * game.player_count
    turn_count = [0] * game.player_count
    darts_in_leg = [0] * game.player_count
    for turn in leg.turns:
        p = turn.player
        s = stats[p]
        turn_count[p] += 1
        s.turns += 1
        s.darts += len(turn.darts)
        darts_in_leg[p] += len(turn.darts)
        # checkout attempts: darts thrown while one dart could have finished
        left = remaining[p]
        for value in turn.values:
            if value and not opened[p]:
                opened[p] = True
            if opened[p] and one_dart_finish(left, game.settings.out_rule):
                s.checkout_attempts += 1
            left -= value
        if turn_count[p] <= FIRST_NINE_TURNS:
            s.first9_darts += len(turn.darts)
            s.first9_points += turn.total
        if turn.bust:
            s.busts += 1
            continue
        s.points += turn.total
        s.highest_turn = max(s.highest_turn, turn.total)
        if bucket := _ton_bucket(turn.total):
            s.tons[bucket] += 1
        remaining[p] -= turn.total
        if turn.checkout:
            s.checkouts += 1
            s.highest_finish = max(s.highest_finish, turn.total)
    _leg_results(leg, stats, darts_in_leg, game.player_count)


def _cricket_leg(game: CricketGame, leg: Leg, stats: list[PlayerGameStats]) -> None:
    darts_in_leg = [0] * game.player_count
    for turn in leg.turns:
        s = stats[turn.player]
        s.turns += 1
        s.darts += len(turn.darts)
        s.marks += sum(turn.values)
        darts_in_leg[turn.player] += len(turn.darts)
    _leg_results(leg, stats, darts_in_leg, game.player_count)


def _leg_results(leg: Leg, stats: list[PlayerGameStats], darts: list[int], players: int) -> None:
    if leg.winner is None:
        return
    for p in range(players):
        stats[p].legs_played += 1
    w = stats[leg.winner]
    w.legs_won += 1
    w.darts_in_won_legs += darts[leg.winner]
    if w.best_leg_darts is None or darts[leg.winner] < w.best_leg_darts:
        w.best_leg_darts = darts[leg.winner]


def _generic_leg(game: Game, leg: Leg, stats: list[PlayerGameStats]) -> None:
    darts_in_leg = [0] * game.player_count
    for turn in leg.turns:
        stats[turn.player].turns += 1
        stats[turn.player].darts += len(turn.darts)
        darts_in_leg[turn.player] += len(turn.darts)
    for p in range(game.player_count):
        result = game.player_result(p)
        stats[p].score = result.get("score")
        stats[p].hits = result.get("hits", 0)
    _leg_results(leg, stats, darts_in_leg, game.player_count)


def game_stats(game: Game) -> list[PlayerGameStats]:
    stats = [PlayerGameStats() for _ in range(game.player_count)]
    for leg in game.legs:
        if isinstance(game, X01Game):
            _x01_leg(game, leg, stats)
        elif isinstance(game, CricketGame):
            _cricket_leg(game, leg, stats)
        elif leg.turns or leg is game.legs[0]:
            _generic_leg(game, leg, stats)
    if game.winner is not None:
        stats[game.winner].won = True
    return stats
