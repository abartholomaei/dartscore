"""Data export (CSV for spreadsheets, JSON for a portable full copy) and per-double statistics.

Both need to know who threw each dart, which is not stored per event: games are replayed with
the game engine, which also gives the score before every dart.
"""

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dartscore.game import Dart, DartEvent, create_game
from dartscore.game.base import Game
from dartscore.game.checkout import one_dart_finish
from dartscore.game.dart import BULL
from dartscore.game.training import BobsGame, DoublesTrainingGame
from dartscore.game.x01 import X01Game
from dartscore.services.games import _event_from_record, _player_info
from dartscore.storage.models import GameEventRecord, GameRecord, Player


def _since(days: int | None) -> datetime | None:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days) if days else None


def iter_darts(record: GameRecord) -> Iterator[tuple[int, Dart, GameEventRecord, Game, int | None]]:
    """Replays a game: yields (thrower position, dart, event, game state *before* the dart,
    targeted double or None) for every dart event."""
    game = create_game(record.mode, len(record.players), record.settings)
    for event in record.events:
        parsed = _event_from_record(event)
        if not isinstance(parsed, DartEvent):
            game.next_turn()
            continue
        thrower = game.current_player
        target = _targeted_double(game, thrower)
        yield thrower, parsed.dart, event, game, target
        game.throw(parsed.dart)
    return


def _targeted_double(game: Game, player: int) -> int | None:
    """The double the player aims at with the next dart, if the mode makes that clear."""
    if isinstance(game, X01Game):
        remaining = game.remaining[player]
        if (
            game.opened[player]
            and game.settings.out_rule == "double"
            and one_dart_finish(remaining, "double")
        ):
            return BULL if remaining == 50 else remaining // 2
        return None
    if isinstance(game, DoublesTrainingGame | BobsGame):
        # the target of the turn the next dart belongs to
        turns = game.turns_of(player)
        index = len(turns) - 1 if game.current_turn is not None else len(turns)
        targets = game.targets if isinstance(game, DoublesTrainingGame) else [*range(1, 21), BULL]
        return targets[min(index, len(targets) - 1)]
    return None


def _dart_label(event: GameEventRecord) -> str | None:
    parsed = _event_from_record(event)
    return parsed.dart.label if isinstance(parsed, DartEvent) else None


class ExportService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def _games(self, session: Session, days: int | None = None) -> list[GameRecord]:
        query = select(GameRecord).where(GameRecord.status != "active").order_by(GameRecord.id)
        if (since := _since(days)) is not None:
            query = query.where(GameRecord.created_at >= since)
        return list(session.scalars(query))

    def games_csv(self) -> str:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            ["game_id", "date", "mode", "status", "player", "guest", "won", "darts", "average",
             "first9_average", "checkout_rate", "highest_finish", "mpr", "score", "hits"]
        )  # fmt: skip
        with self._sessions() as session:
            for record in self._games(session):
                for gp in record.players:
                    info, s = _player_info(gp), gp.stats or {}
                    writer.writerow(
                        [record.id, record.created_at.isoformat(), record.mode, record.status,
                         info["name"], info["guest"], record.winner_position == gp.position,
                         s.get("darts"), s.get("average"), s.get("first9_average"),
                         s.get("checkout_rate"), s.get("highest_finish"), s.get("mpr"),
                         s.get("score"), s.get("hits")]
                    )  # fmt: skip
        return out.getvalue()

    def darts_csv(self) -> str:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            ["game_id", "seq", "date", "mode", "player", "dart", "points", "x_mm", "y_mm",
             "source", "confidence"]
        )  # fmt: skip
        with self._sessions() as session:
            for record in self._games(session):
                names = [_player_info(gp)["name"] for gp in record.players]
                for thrower, dart, event, _, _ in iter_darts(record):
                    writer.writerow(
                        [record.id, event.seq, event.created_at.isoformat(), record.mode,
                         names[thrower], dart.label, dart.points, event.x_mm, event.y_mm,
                         event.source, event.confidence]
                    )  # fmt: skip
        return out.getvalue()

    def all_json(self) -> dict[str, Any]:
        with self._sessions() as session:
            players = [
                {
                    "id": p.id,
                    "name": p.name,
                    "color": p.color,
                    "created_at": p.created_at.isoformat(),
                    "archived": p.archived_at is not None,
                    "favorite_double": p.favorite_double,
                }
                for p in session.scalars(select(Player).order_by(Player.id))
            ]
            games = [
                {
                    "id": r.id,
                    "mode": r.mode,
                    "settings": r.settings,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                    "winner": r.winner_position,
                    "players": [{**_player_info(gp), "stats": gp.stats} for gp in r.players],
                    "events": [
                        {
                            "seq": e.seq,
                            "kind": e.kind,
                            "dart": _dart_label(e),
                            "x_mm": e.x_mm,
                            "y_mm": e.y_mm,
                            "source": e.source,
                            "confidence": e.confidence,
                        }
                        for e in r.events
                    ],
                }
                for r in self._games(session)
            ]
        return {
            "exported_at": datetime.now(UTC).isoformat(),
            "format": "dartscore-1",
            "players": players,
            "games": games,
        }

    def double_rates(self, player_id: int, days: int | None = None) -> dict[str, dict[str, int]]:
        """Attempts and hits per double (1-20, 25 = bull) for a player."""
        rates: dict[str, dict[str, int]] = {}
        with self._sessions() as session:
            for record in self._games(session, days):
                positions = [gp.position for gp in record.players if gp.player_id == player_id]
                if not positions:
                    continue
                for thrower, dart, _, _, target in iter_darts(record):
                    if thrower not in positions or target is None:
                        continue
                    entry = rates.setdefault(str(target), {"attempts": 0, "hits": 0})
                    entry["attempts"] += 1
                    entry["hits"] += int(dart.segment == target and dart.is_double)
        return rates
