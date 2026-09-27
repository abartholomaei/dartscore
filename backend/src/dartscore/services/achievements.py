"""Achievements: milestones a player reaches, derived from the stored games (nothing extra is
stored). Games are replayed oldest first so each achievement carries the game it was first
reached in."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dartscore.game import Game, replay_game
from dartscore.game.base import Leg, Turn
from dartscore.game.dart import BULL
from dartscore.game.x01 import X01Game
from dartscore.services.games import _event_from_record
from dartscore.storage.models import GamePlayer, GameRecord

# in display order
ACHIEVEMENTS = (
    "first_game",
    "first_win",
    "ton",
    "ton_forty",
    "one_eighty",
    "hat_trick",
    "ton_out",
    "big_fish",
    "bull_finish",
    "leg_15",
    "leg_12",
    "nine_darter",
    "average_60",
    "average_80",
    "average_100",
    "white_horse",
    "mpr_3",
    "shanghai",
    "round_the_clock",
    "games_10",
    "games_100",
)


@dataclass
class _Context:
    record: GameRecord
    game: Game
    position: int
    stats: dict[str, Any]


def _turns(ctx: _Context) -> Iterator[Turn]:
    for leg in ctx.game.legs:
        yield from ctx.game.turns_of(ctx.position, leg)


def _won_legs(ctx: _Context) -> Iterator[Leg]:
    return (leg for leg in ctx.game.legs if leg.winner == ctx.position)


def _x01(ctx: _Context) -> bool:
    return ctx.record.mode == "x01"


def _any_turn(ctx: _Context, check: Callable[[Turn], bool]) -> bool:
    return any(check(turn) for turn in _turns(ctx))


def _total(turn: Turn) -> int:
    return 0 if turn.bust else sum(turn.values)


def _checkouts(ctx: _Context) -> Iterator[Turn]:
    return (t for t in _turns(ctx) if t.checkout) if _x01(ctx) else iter(())


def _fastest_leg(ctx: _Context) -> int | None:
    if not _x01(ctx) or not isinstance(ctx.game, X01Game):
        return None
    if ctx.game.settings.start_for(ctx.position) != 501:  # handicap starts do not count
        return None
    darts = [
        sum(len(t.darts) for t in ctx.game.turns_of(ctx.position, leg)) for leg in _won_legs(ctx)
    ]
    return min(darts, default=None)


def _is_shanghai(turn: Turn) -> bool:
    segments = {d.segment for d in turn.darts}
    return (
        len(turn.darts) == 3
        and len(segments) == 1
        and 0 not in segments
        and sorted(d.multiplier for d in turn.darts) == [1, 2, 3]
    )


def _is_white_horse(turn: Turn) -> bool:
    triples = {d.segment for d in turn.darts if d.is_triple and 15 <= d.segment <= 20}
    return len(triples) == 3


def _average(ctx: _Context, minimum: float) -> bool:
    average = ctx.stats.get("average")
    return _x01(ctx) and (ctx.stats.get("darts") or 0) >= 9 and (average or 0) >= minimum


def _leg_within(darts: int) -> Callable[[_Context], bool]:
    def check(ctx: _Context) -> bool:
        fastest = _fastest_leg(ctx)
        return fastest is not None and fastest <= darts

    return check


# per-game checks; counters (games_10, ...) are handled separately
_CHECKS: dict[str, Callable[[_Context], bool]] = {
    "first_game": lambda ctx: ctx.record.status == "finished",
    "first_win": lambda ctx: (
        len(ctx.record.players) > 1 and ctx.record.winner_position == ctx.position
    ),
    "ton": lambda ctx: _x01(ctx) and _any_turn(ctx, lambda t: _total(t) >= 100),
    "ton_forty": lambda ctx: _x01(ctx) and _any_turn(ctx, lambda t: _total(t) >= 140),
    "one_eighty": lambda ctx: _x01(ctx) and _any_turn(ctx, lambda t: _total(t) == 180),
    "hat_trick": lambda ctx: _any_turn(
        ctx, lambda t: len(t.darts) == 3 and all(d.segment == BULL for d in t.darts)
    ),
    "ton_out": lambda ctx: any(_total(t) >= 100 for t in _checkouts(ctx)),
    "big_fish": lambda ctx: any(_total(t) == 170 for t in _checkouts(ctx)),
    "bull_finish": lambda ctx: any(
        t.darts[-1].segment == BULL and t.darts[-1].is_double for t in _checkouts(ctx)
    ),
    "leg_15": _leg_within(15),
    "leg_12": _leg_within(12),
    "nine_darter": _leg_within(9),
    "average_60": lambda ctx: _average(ctx, 60),
    "average_80": lambda ctx: _average(ctx, 80),
    "average_100": lambda ctx: _average(ctx, 100),
    "white_horse": lambda ctx: ctx.record.mode == "cricket" and _any_turn(ctx, _is_white_horse),
    "mpr_3": lambda ctx: (
        ctx.record.mode == "cricket"
        and (ctx.stats.get("darts") or 0) >= 9
        and (ctx.stats.get("mpr") or 0) >= 3
    ),
    "shanghai": lambda ctx: _any_turn(ctx, _is_shanghai),
    "round_the_clock": lambda ctx: (
        ctx.record.mode == "around_the_clock"
        and ctx.record.status == "finished"
        and (ctx.game.state().get("current_targets") or [""])[ctx.position] is None
    ),
}

_COUNTERS = {"games_10": 10, "games_100": 100}


class AchievementService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def for_player(self, player_id: int) -> list[dict[str, Any]]:
        """All achievements in display order; ``achieved_at``/``game_id`` are None while locked."""
        reached: dict[str, tuple[str, int]] = {}
        with self._sessions() as session:
            rows = session.execute(
                select(GameRecord, GamePlayer)
                .join(GamePlayer, GamePlayer.game_id == GameRecord.id)
                .where(GamePlayer.player_id == player_id, GameRecord.status == "finished")
                .order_by(GameRecord.id)
            ).all()
            for count, (record, gp) in enumerate(rows, start=1):
                when = (record.finished_at or record.created_at).isoformat()
                for key, needed in _COUNTERS.items():
                    if count >= needed:
                        reached.setdefault(key, (when, record.id))
                if all(key in reached for key in _CHECKS):
                    continue
                if record.settings.get("teams"):
                    continue  # team results are not personal achievements
                events = [_event_from_record(e) for e in record.events]
                game = replay_game(record.mode, len(record.players), record.settings, events)
                ctx = _Context(record, game, gp.position, gp.stats or {})
                for key, check in _CHECKS.items():
                    if key not in reached and check(ctx):
                        reached[key] = (when, record.id)
        return [
            {
                "id": key,
                "achieved_at": reached[key][0] if key in reached else None,
                "game_id": reached[key][1] if key in reached else None,
            }
            for key in ACHIEVEMENTS
        ]
