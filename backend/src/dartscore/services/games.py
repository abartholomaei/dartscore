"""Runs the active game: applies darts, persists every event immediately, broadcasts state.

Only one game can be active at a time (there is one board). Every change is written to the
database before the new state is published, so a crash or power loss loses nothing.
"""

import threading
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dartscore.game import (
    Dart,
    DartEvent,
    Event,
    Game,
    GameError,
    NextEvent,
    create_game,
    replay_game,
)
from dartscore.game.stats import game_stats
from dartscore.services.hub import EventHub
from dartscore.storage.models import GameEventRecord, GamePlayer, GameRecord, Player, utcnow

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PlayerRef:
    """A game participant: a profile (player_id) or a guest (guest_name)."""

    player_id: int | None = None
    guest_name: str | None = None


@dataclass
class EventMeta:
    source: str = "manual"
    x_mm: float | None = None
    y_mm: float | None = None


@dataclass
class ActiveGame:
    id: int
    game: Game
    players: list[dict[str, Any]]
    created_at: str
    meta: list[EventMeta] = field(default_factory=list)


def _event_from_record(record: GameEventRecord) -> Event:
    if record.kind == "dart":
        assert record.segment is not None
        assert record.multiplier is not None
        return DartEvent(Dart(record.segment, record.multiplier))
    return NextEvent()


def _player_info(gp: GamePlayer) -> dict[str, Any]:
    if gp.player is not None:
        return {
            "position": gp.position,
            "player_id": gp.player_id,
            "name": gp.player.name,
            "color": gp.player.color,
            "guest": False,
        }
    return {
        "position": gp.position,
        "player_id": None,
        "name": gp.guest_name or f"Guest {gp.position + 1}",
        "color": "#9e9e9e",
        "guest": True,
    }


class GameService:
    def __init__(self, sessions: sessionmaker[Session], hub: EventHub) -> None:
        self._sessions = sessions
        self._hub = hub
        self._lock = threading.RLock()
        self._active: ActiveGame | None = None
        self._load_active()

    # --- queries ------------------------------------------------------------------------

    def active_state(self) -> dict[str, Any] | None:
        with self._lock:
            return self._state(self._active) if self._active else None

    def game_state(self, game_id: int) -> dict[str, Any]:
        with self._lock:
            if self._active and self._active.id == game_id:
                return self._state(self._active)
        with self._sessions() as session:
            return self._state(self._load(session, game_id))

    def history(self, limit: int = 20, player_id: int | None = None) -> list[dict[str, Any]]:
        with self._sessions() as session:
            query = select(GameRecord).where(GameRecord.status != "active")
            if player_id is not None:
                query = query.where(
                    GameRecord.id.in_(
                        select(GamePlayer.game_id).where(GamePlayer.player_id == player_id)
                    )
                )
            records = session.scalars(query.order_by(GameRecord.id.desc()).limit(limit))
            return [
                {
                    "id": r.id,
                    "mode": r.mode,
                    "settings": r.settings,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    "winner": r.winner_position,
                    "players": [{**_player_info(gp), "stats": gp.stats} for gp in r.players],
                }
                for r in records
            ]

    # --- commands -----------------------------------------------------------------------

    def create(
        self,
        mode: str,
        settings: dict[str, Any],
        players: list[PlayerRef],
        abort_active: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            if self._active is not None:
                if not self._active.game.finished:
                    if not abort_active:
                        raise GameError("game_active", "Another game is still running")
                    self._set_status(self._active.id, "aborted")
                # a finished game keeps its status and just makes room for the new one
                self._active = None
            game = create_game(mode, len(players), settings)
            with self._sessions() as session:
                record = GameRecord(mode=mode, settings=game.settings_dict())
                for position, ref in enumerate(players):
                    if ref.player_id is not None:
                        player = session.get(Player, ref.player_id)
                        if player is None or player.archived_at is not None:
                            raise GameError("player_not_found", f"Player {ref.player_id} not found")
                        gp = GamePlayer(position=position, player_id=ref.player_id)
                    else:
                        name = " ".join((ref.guest_name or "").split())[:40] or None
                        gp = GamePlayer(position=position, guest_name=name)
                    record.players.append(gp)
                session.add(record)
                session.commit()
                session.refresh(record)
                self._active = ActiveGame(
                    id=record.id,
                    game=game,
                    players=[_player_info(gp) for gp in record.players],
                    created_at=record.created_at.isoformat(),
                )
            log.info("game_started", game_id=record.id, mode=mode, players=len(players))
            return self._publish()

    def throw(
        self,
        dart: Dart,
        source: str = "manual",
        x_mm: float | None = None,
        y_mm: float | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            active = self._require_active()
            active.game.throw(dart)
            active.meta.append(EventMeta(source, x_mm, y_mm))
            self._append_event(active)
            return self._after_change(active)

    def next_turn(self) -> dict[str, Any]:
        with self._lock:
            active = self._require_active()
            active.game.next_turn()
            active.meta.append(EventMeta("manual"))
            self._append_event(active)
            return self._after_change(active)

    def undo(self) -> dict[str, Any]:
        with self._lock:
            active = self._require_active()
            active.game.undo()
            active.meta.pop()
            with self._sessions() as session:
                last = session.scalars(
                    select(GameEventRecord)
                    .where(GameEventRecord.game_id == active.id)
                    .order_by(GameEventRecord.seq.desc())
                    .limit(1)
                ).first()
                if last is not None:
                    session.delete(last)
                    session.commit()
            return self._after_change(active)

    def correct(self, turn_index: int, dart_index: int, dart: Dart) -> dict[str, Any]:
        with self._lock:
            active = self._require_active()
            before = list(active.game.events)
            active.game.replace_dart(turn_index, dart_index, dart)
            changed = [
                i for i, (a, b) in enumerate(zip(before, active.game.events, strict=True)) if a != b
            ]
            with self._sessions() as session:
                for seq in changed:
                    record = session.scalars(
                        select(GameEventRecord).where(
                            GameEventRecord.game_id == active.id, GameEventRecord.seq == seq
                        )
                    ).one()
                    record.segment, record.multiplier = dart.segment, dart.multiplier
                    record.source = "corrected"
                    active.meta[seq].source = "corrected"
                session.commit()
            return self._after_change(active)

    def abort(self) -> None:
        with self._lock:
            active = self._require_active()
            self._set_status(active.id, "aborted")
            self._active = None
            log.info("game_aborted", game_id=active.id)
            self._hub.publish("game", None)

    def rematch(self) -> dict[str, Any]:
        """Same settings and players; the starting order rotates by one."""
        with self._lock:
            with self._sessions() as session:
                last = session.scalars(
                    select(GameRecord).order_by(GameRecord.id.desc()).limit(1)
                ).first()
                if last is None:
                    raise GameError("no_game", "No previous game")
                refs = [PlayerRef(gp.player_id, gp.guest_name) for gp in last.players]
                mode, settings = last.mode, dict(last.settings)
            refs = refs[1:] + refs[:1]
            return self.create(mode, settings, refs, abort_active=True)

    # --- internals ----------------------------------------------------------------------

    def _require_active(self) -> ActiveGame:
        if self._active is None:
            raise GameError("no_active_game", "No game is running")
        return self._active

    def _load(self, session: Session, game_id: int) -> ActiveGame:
        record = session.get(GameRecord, game_id)
        if record is None:
            raise GameError("game_not_found", f"Game {game_id} not found")
        events = [_event_from_record(e) for e in record.events]
        game = replay_game(record.mode, len(record.players), record.settings, events)
        return ActiveGame(
            id=record.id,
            game=game,
            players=[_player_info(gp) for gp in record.players],
            created_at=record.created_at.isoformat(),
            meta=[EventMeta(e.source, e.x_mm, e.y_mm) for e in record.events],
        )

    def _load_active(self) -> None:
        with self._sessions() as session:
            record = session.scalars(
                select(GameRecord)
                .where(GameRecord.status == "active")
                .order_by(GameRecord.id.desc())
            ).first()
            if record is None:
                return
            try:
                self._active = self._load(session, record.id)
                log.info("game_resumed", game_id=record.id)
            except GameError as exc:
                log.error("game_resume_failed", game_id=record.id, error=str(exc))
                record.status = "aborted"
                session.commit()

    def _append_event(self, active: ActiveGame) -> None:
        seq = len(active.game.events) - 1
        event = active.game.events[seq]
        meta = active.meta[seq]
        with self._sessions() as session:
            record = GameEventRecord(
                game_id=active.id,
                seq=seq,
                kind=event.kind,
                source=meta.source,
                x_mm=meta.x_mm,
                y_mm=meta.y_mm,
            )
            if isinstance(event, DartEvent):
                record.segment, record.multiplier = event.dart.segment, event.dart.multiplier
            session.add(record)
            session.commit()

    def _after_change(self, active: ActiveGame) -> dict[str, Any]:
        """Stores statistics and the result, then publishes the new state."""
        game = active.game
        stats = game_stats(game)
        with self._sessions() as session:
            record = session.get(GameRecord, active.id)
            assert record is not None
            for gp in record.players:
                gp.stats = stats[gp.position].to_dict()
            if game.finished and record.status != "finished":
                record.status, record.finished_at, record.winner_position = (
                    "finished",
                    utcnow(),
                    game.winner,
                )
                log.info("game_finished", game_id=active.id, winner=game.winner)
            elif not game.finished and record.status == "finished":
                # the winning dart was undone
                record.status, record.finished_at, record.winner_position = "active", None, None
            session.commit()
        return self._publish()

    def _set_status(self, game_id: int, status: str) -> None:
        with self._sessions() as session:
            record = session.get(GameRecord, game_id)
            if record is not None:
                record.status = status
                record.finished_at = utcnow()
                session.commit()

    def _publish(self) -> dict[str, Any]:
        state = self._state(self._active) if self._active else None
        self._hub.publish("game", state)
        return state or {}

    def _state(self, active: ActiveGame) -> dict[str, Any]:
        game = active.game
        state = game.state()
        leg = game.legs[-1]
        # the finished leg stays visible until the darts are pulled
        if state["leg_winner"] is not None and len(game.legs) > 1 and not game.finished:
            leg = game.legs[-2]
        stats = game_stats(game)
        return {
            "id": active.id,
            "created_at": active.created_at,
            "players": [
                {**info, "stats": stats[info["position"]].to_dict()} for info in active.players
            ],
            "history": [
                {
                    "player": t.player,
                    "darts": [d.label for d in t.darts],
                    "total": t.total,
                    "bust": t.bust,
                    "checkout": t.checkout,
                }
                for t in leg.turns
            ],
            **state,
        }
