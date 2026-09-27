"""Statistics across games: per player (by mode) and head-to-head."""

import math
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased, sessionmaker

from dartscore.game import GameError
from dartscore.game.teams import current_member, engine_players, teams_of
from dartscore.services.avatars import avatar_url
from dartscore.services.export import _since
from dartscore.storage.models import GamePlayer, GameRecord, Player

_SUMMED = (
    "darts",
    "turns",
    "legs_played",
    "legs_won",
    "points",
    "first9_points",
    "first9_darts",
    "checkout_attempts",
    "checkouts",
    "darts_in_won_legs",
    "busts",
    "marks",
    "hits",
)


def _ratio(a: float, b: float, factor: float = 1.0, digits: int = 2) -> float | None:
    return round(a / b * factor, digits) if b else None


def _aggregate(rows: list[tuple[GameRecord, GamePlayer]]) -> dict[str, Any]:
    total: dict[str, Any] = dict.fromkeys(_SUMMED, 0)
    total.update(
        games=0,
        wins=0,
        highest_finish=0,
        highest_turn=0,
        best_leg_darts=None,
        tons={"60": 0, "100": 0, "140": 0, "180": 0},
        best_score=None,
        score_sum=0,
        scored_games=0,
    )
    trend = []
    for record, gp in rows:
        if record.settings.get("teams"):
            continue  # team games: the averages are the team's, not the player's
        s = gp.stats or {}
        total["games"] += 1
        total["wins"] += int(record.winner_position == gp.position)
        for key in _SUMMED:
            total[key] += s.get(key, 0) or 0
        total["highest_finish"] = max(total["highest_finish"], s.get("highest_finish", 0) or 0)
        total["highest_turn"] = max(total["highest_turn"], s.get("highest_turn", 0) or 0)
        best = s.get("best_leg_darts")
        if best is not None and (total["best_leg_darts"] is None or best < total["best_leg_darts"]):
            total["best_leg_darts"] = best
        score = s.get("score")
        if score is not None:
            total["scored_games"] += 1
            total["score_sum"] += score
            if total["best_score"] is None or score > total["best_score"]:
                total["best_score"] = score
        for bucket, count in (s.get("tons") or {}).items():
            total["tons"][bucket] = total["tons"].get(bucket, 0) + count
        trend.append(
            {
                "game_id": record.id,
                "date": record.created_at.isoformat(),
                "average": s.get("average"),
                "mpr": s.get("mpr"),
                "score": s.get("score"),
                "won": record.winner_position == gp.position,
            }
        )
    total.update(
        average=_ratio(total["points"], total["darts"], 3),
        first9_average=_ratio(total["first9_points"], total["first9_darts"], 3),
        checkout_rate=_ratio(total["checkouts"], total["checkout_attempts"], digits=4),
        mpr=_ratio(total["marks"], total["darts"], 3),
        win_rate=_ratio(total["wins"], total["games"], digits=4),
        darts_per_leg=_ratio(total["darts_in_won_legs"], total["legs_won"], digits=1),
        average_score=_ratio(total["score_sum"], total["scored_games"], digits=1),
        hit_rate=_ratio(total["hits"], total["darts"], digits=4) if total["scored_games"] else None,
        trend=trend,
    )
    return total


class StatsService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def player(self, player_id: int, days: int | None = None) -> dict[str, Any]:
        """Statistics per mode; ``days`` limits them to the most recent days."""
        with self._sessions() as session:
            player = session.get(Player, player_id)
            if player is None:
                raise GameError("player_not_found", f"Player {player_id} not found")
            rows = session.execute(
                select(GameRecord, GamePlayer)
                .join(GamePlayer, GamePlayer.game_id == GameRecord.id)
                .where(
                    GamePlayer.player_id == player_id,
                    GameRecord.status == "finished",
                    GameRecord.created_at >= (_since(days) or datetime.min),
                )
                .order_by(GameRecord.id)
            ).all()
            by_mode: dict[str, list[tuple[GameRecord, GamePlayer]]] = {}
            for record, gp in rows:
                by_mode.setdefault(record.mode, []).append((record, gp))
            return {
                "player": {
                    "id": player.id,
                    "name": player.name,
                    "color": player.color,
                    "avatar": avatar_url(player.id, player.avatar),
                },
                "modes": {mode: _aggregate(items) for mode, items in by_mode.items()},
            }

    def head_to_head(self, a: int, b: int) -> dict[str, Any]:
        with self._sessions() as session:
            ga, gb = aliased(GamePlayer), aliased(GamePlayer)
            rows = session.execute(
                select(GameRecord, ga, gb)
                .join(ga, ga.game_id == GameRecord.id)
                .join(gb, gb.game_id == GameRecord.id)
                .where(ga.player_id == a, gb.player_id == b, GameRecord.status == "finished")
                .order_by(GameRecord.id)
            ).all()
            wins_a = sum(1 for r, pa, _ in rows if r.winner_position == pa.position)
            wins_b = sum(1 for r, _, pb in rows if r.winner_position == pb.position)
            return {
                "games": len(rows),
                "wins": {str(a): wins_a, str(b): wins_b},
                "stats": {
                    str(a): _aggregate([(r, pa) for r, pa, _ in rows]),
                    str(b): _aggregate([(r, pb) for r, _, pb in rows]),
                },
            }


def player_positions(
    sessions: sessionmaker[Session], player_id: int, limit: int = 3000
) -> list[tuple[float, float, str]]:
    """Board positions of the player's detected darts (for a heatmap), newest first."""
    from dartscore.game import Dart, replay_game
    from dartscore.game.base import DartEvent
    from dartscore.services.games import _event_from_record

    result: list[tuple[float, float, str]] = []
    with sessions() as session:
        games = session.execute(
            select(GameRecord, GamePlayer)
            .join(GamePlayer, GamePlayer.game_id == GameRecord.id)
            .where(GamePlayer.player_id == player_id, GameRecord.status != "active")
            .order_by(GameRecord.id.desc())
        ).all()
        for record, gp in games:
            events = list(record.events)
            if not any(e.x_mm is not None for e in events):
                continue
            # replay to know whose turn each dart was
            teams = teams_of(record.settings)
            game = replay_game(
                record.mode,
                engine_players(record.settings, len(record.players)),
                record.settings,
                [],
            )
            for event in events:
                parsed = _event_from_record(event)
                if isinstance(parsed, DartEvent):
                    thrower = current_member(game, teams) if teams else game.current_player
                    if thrower == gp.position and event.x_mm is not None and event.y_mm is not None:
                        label = Dart(parsed.dart.segment, parsed.dart.multiplier).label
                        result.append((round(event.x_mm, 1), round(event.y_mm, 1), label))
                        if len(result) >= limit:
                            return result
                    game.throw(parsed.dart)
                else:
                    game.next_turn()
    return result


def player_grouping(sessions: sessionmaker[Session], player_id: int) -> dict[str, Any]:
    """How tight the player's turns are: the mean distance (mm) of the darts of a turn from their
    centre, for turns whose three darts were all detected. Newest turns first in ``recent``."""
    from dartscore.game import replay_game
    from dartscore.game.base import DartEvent
    from dartscore.services.games import _event_from_record

    spreads: list[float] = []
    with sessions() as session:
        games = session.execute(
            select(GameRecord, GamePlayer)
            .join(GamePlayer, GamePlayer.game_id == GameRecord.id)
            .where(GamePlayer.player_id == player_id, GameRecord.status != "active")
            .order_by(GameRecord.id)
        ).all()
        for record, gp in games:
            events = list(record.events)
            if not any(e.x_mm is not None for e in events):
                continue
            teams = teams_of(record.settings)
            game = replay_game(
                record.mode,
                engine_players(record.settings, len(record.players)),
                record.settings,
                [],
            )
            turn: list[tuple[float, float]] = []
            for event in events:
                parsed = _event_from_record(event)
                if not isinstance(parsed, DartEvent):
                    game.next_turn()
                    continue
                if game.current_turn is None:
                    turn = []  # a new turn begins
                thrower = current_member(game, teams) if teams else game.current_player
                if thrower == gp.position:
                    if event.x_mm is not None and event.y_mm is not None:
                        turn.append((event.x_mm, event.y_mm))
                    if len(turn) == 3:
                        cx = sum(x for x, _ in turn) / 3
                        cy = sum(y for _, y in turn) / 3
                        spreads.append(sum(math.hypot(x - cx, y - cy) for x, y in turn) / 3)
                game.throw(parsed.dart)
    recent = spreads[-50:]
    return {
        "turns": len(spreads),
        "average_mm": round(sum(spreads) / len(spreads), 1) if spreads else None,
        "recent_mm": round(sum(recent) / len(recent), 1) if recent else None,
        "best_mm": round(min(spreads), 1) if spreads else None,
    }
