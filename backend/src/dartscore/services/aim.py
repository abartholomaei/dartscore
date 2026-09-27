"""Aim deviation: how far and in which direction a player's darts miss the field they aimed at.

The intended field is only known in some situations: a double on a finish, doubles training,
Bob's 27, segment training with a fixed ring - and, as an assumption, the treble 20 while
scoring in X01 (only darts landing near it count, so switching to T19 does not distort it).

Deviation is split relative to the target: "radial" = towards the outside of the board
(for the 20: too high) and "sideways" = clockwise (for the 20: to the right).
"""

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dartscore.game.base import Game
from dartscore.game.dart import BULL, Dart
from dartscore.game.practice import RING_MULTIPLIER, SegmentTrainingGame
from dartscore.game.x01 import X01Game
from dartscore.services.bot import aim_point
from dartscore.services.export import _since, _targeted_double, iter_darts
from dartscore.storage.models import GamePlayer, GameRecord

# X01 scoring darts count for the T20 only within this distance of it (mm)
T20_RADIUS_MM = 60.0
# detections that were corrected have a wrong position
_TRUSTED_SOURCES = ("auto",)


def intended_target(game: Game, player: int) -> Dart | None:
    """The field the next dart of ``player`` is aimed at, if the situation makes it clear."""
    double = _targeted_double(game, player)
    if double is not None:
        return Dart(double, 2)
    if isinstance(game, SegmentTrainingGame):
        multiplier = RING_MULTIPLIER[game.settings.ring]
        if multiplier is None:
            return None
        index = len(game.turns_of(player)) - (1 if game.current_turn is not None else 0)
        target = game.target_for(player, index)
        if target == BULL:
            return Dart(BULL, 2 if multiplier == 2 else 1)
        return Dart(target, multiplier)
    if isinstance(game, X01Game) and game.opened[player] and game.remaining[player] > 170:
        return Dart(20, 3)
    return None


def _label(target: Dart) -> str:
    if target.multiplier == 3 and target.segment == 20:
        return "T20"
    return (
        "BULL"
        if target.segment == BULL
        else ("doubles" if target.multiplier == 2 else target.label)
    )


def aim_stats(
    sessions: sessionmaker[Session], player_id: int, days: int | None = None
) -> dict[str, Any]:
    groups: dict[str, list[tuple[float, float]]] = {}
    with sessions() as session:
        query = (
            select(GameRecord, GamePlayer)
            .join(GamePlayer, GamePlayer.game_id == GameRecord.id)
            .where(GamePlayer.player_id == player_id, GameRecord.status != "active")
            .order_by(GameRecord.id)
        )
        if (since := _since(days)) is not None:
            query = query.where(GameRecord.created_at >= since)
        for record, gp in session.execute(query).all():
            if not any(e.x_mm is not None for e in record.events):
                continue
            for thrower, _dart, event, game, _double in iter_darts(record):
                if thrower != gp.position or event.x_mm is None or event.y_mm is None:
                    continue
                if event.source not in _TRUSTED_SOURCES:
                    continue
                target = intended_target(game, thrower)
                if target is None:
                    continue
                tx, ty = aim_point(target)
                dx, dy = event.x_mm - tx, event.y_mm - ty
                if target.label == "T20" and math.hypot(dx, dy) > T20_RADIUS_MM:
                    continue
                if target.segment == BULL:
                    # no direction around the bull: outward = up, sideways = right
                    radial, sideways = dy, dx
                else:
                    angle = math.atan2(ty, tx)
                    radial = dx * math.cos(angle) + dy * math.sin(angle)
                    sideways = dx * math.sin(angle) - dy * math.cos(angle)
                groups.setdefault(_label(target), []).append((radial, sideways))

    def summary(points: list[tuple[float, float]]) -> dict[str, Any]:
        n = len(points)
        return {
            "darts": n,
            "radial_mm": round(sum(p[0] for p in points) / n, 1),
            "sideways_mm": round(sum(p[1] for p in points) / n, 1),
            "distance_mm": round(sum(math.hypot(*p) for p in points) / n, 1),
            # the latest darts for a scatter plot (radial, sideways)
            "points": [(round(r, 1), round(s, 1)) for r, s in points[-150:]],
        }

    everything = [p for points in groups.values() for p in points]
    return {
        "overall": summary(everything) if everything else None,
        "targets": {name: summary(points) for name, points in groups.items()},
    }
