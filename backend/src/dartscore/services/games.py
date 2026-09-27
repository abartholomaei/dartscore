"""Runs the active game: applies darts, persists every event immediately, broadcasts state.

Only one game can be active at a time (there is one board). Every change is written to the
database before the new state is published, so a crash or power loss loses nothing.
"""

import threading
from collections.abc import Callable
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
from dartscore.game.teams import current_member, engine_players, teams_of, validate_teams
from dartscore.services.avatars import avatar_url
from dartscore.services.hub import EventHub
from dartscore.storage.models import GameEventRecord, GamePlayer, GameRecord, Player, utcnow

log = structlog.get_logger(__name__)

BOT_MODES = ("x01", "cricket")


@dataclass(frozen=True)
class PlayerRef:
    """A game participant: a profile (player_id) or a guest (guest_name)."""

    player_id: int | None = None
    guest_name: str | None = None
    bot_level: int | None = None
    # personal bot: imitates this player (bot_level is then that player's average)
    bot_of: int | None = None


@dataclass
class EventMeta:
    source: str = "manual"
    x_mm: float | None = None
    y_mm: float | None = None
    confidence: float | None = None


@dataclass
class ActiveGame:
    id: int
    game: Game
    players: list[dict[str, Any]]
    created_at: str
    meta: list[EventMeta] = field(default_factory=list)
    # the stored settings (including "teams" for team games)
    settings: dict[str, Any] = field(default_factory=dict)


def _event_from_record(record: GameEventRecord) -> Event:
    if record.kind == "dart":
        assert record.segment is not None
        assert record.multiplier is not None
        # the detected position only for darts nobody corrected (a correction means the
        # detection was wrong; a bounce-out fell out of the board)
        position = (
            (record.x_mm, record.y_mm)
            if record.source in ("auto", "bot", "manual")
            and record.x_mm is not None
            and record.y_mm is not None
            else None
        )
        return DartEvent(Dart(record.segment, record.multiplier), position=position)
    return NextEvent()


def _player_info(gp: GamePlayer) -> dict[str, Any]:
    if gp.player is not None:
        return {
            "position": gp.position,
            "player_id": gp.player_id,
            "name": gp.player.name,
            "color": gp.player.color,
            "avatar": avatar_url(gp.player.id, gp.player.avatar),
            "guest": False,
            "bot_level": None,
            "bot_of": None,
        }
    return {
        "position": gp.position,
        "player_id": None,
        "name": gp.guest_name or f"Guest {gp.position + 1}",
        "color": "#9e9e9e",
        "guest": True,
        "bot_level": gp.bot_level,
        "bot_of": gp.bot_of,
    }


class GameService:
    def __init__(self, sessions: sessionmaker[Session], hub: EventHub) -> None:
        self._sessions = sessions
        self._hub = hub
        self._lock = threading.RLock()
        self._active: ActiveGame | None = None
        self._listeners: list[Callable[[str], None]] = []
        self._load_active()

    def add_listener(self, listener: Callable[[str], None]) -> None:
        """Called with "next" or "new_game" after the change (e.g. to sync the detector) and
        "change" after every published state."""
        self._listeners.append(listener)

    def _notify(self, event: str) -> None:
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                log.exception("game_listener_failed", event=event)

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
            teams = teams_of(settings)
            if teams is not None:
                teams = validate_teams(teams, len(players))
                if mode not in BOT_MODES:
                    raise GameError("invalid_teams", "Teams play X01 or Cricket")
                if any(ref.bot_level for ref in players):
                    raise GameError("invalid_teams", "Bots cannot play in teams")
            with self._sessions() as session:
                if mode == "x01" and "preferred_doubles" not in settings and teams is None:
                    # checkout suggestions use each profile's favourite double
                    favourites = []
                    for ref in players:
                        player = session.get(Player, ref.player_id) if ref.player_id else None
                        favourites.append(player.favorite_double if player else None)
                    settings = {**settings, "preferred_doubles": favourites}
            if any(ref.bot_level for ref in players) and mode not in BOT_MODES:
                raise GameError("bot_mode", f"Bots can only play {', '.join(BOT_MODES)}")
            game = create_game(mode, len(teams) if teams else len(players), settings)
            stored = game.settings_dict() | ({"teams": teams} if teams else {})
            with self._sessions() as session:
                record = GameRecord(mode=mode, settings=stored)
                for position, ref in enumerate(players):
                    if ref.player_id is not None:
                        player = session.get(Player, ref.player_id)
                        if player is None or player.archived_at is not None:
                            raise GameError("player_not_found", f"Player {ref.player_id} not found")
                        gp = GamePlayer(position=position, player_id=ref.player_id)
                    elif ref.bot_level:
                        bot_name = f"Bot {ref.bot_level}"
                        if ref.bot_of is not None:
                            model = session.get(Player, ref.bot_of)
                            if model is None:
                                raise GameError(
                                    "player_not_found", f"Player {ref.bot_of} not found"
                                )
                            bot_name = f"{model.name} (Bot)"[:40]
                        gp = GamePlayer(
                            position=position,
                            guest_name=bot_name,
                            bot_level=ref.bot_level,
                            bot_of=ref.bot_of,
                        )
                    else:
                        name = " ".join((ref.guest_name or "").split())[:40] or None
                        gp = GamePlayer(position=position, guest_name=name)
                    record.players.append(gp)
                session.add(record)
                session.commit()
                session.refresh(record)
                self._active = ActiveGame(
                    id=record.id,
                    settings=dict(record.settings),
                    game=game,
                    players=[_player_info(gp) for gp in record.players],
                    created_at=record.created_at.isoformat(),
                )
            log.info("game_started", game_id=record.id, mode=mode, players=len(players))
            self._notify("new_game")
            return self._publish()

    def throw(
        self,
        dart: Dart,
        source: str = "manual",
        x_mm: float | None = None,
        y_mm: float | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            active = self._require_active()
            self._check_bot(active, source)
            position = (x_mm, y_mm) if x_mm is not None and y_mm is not None else None
            active.game.throw(dart, position)
            active.meta.append(EventMeta(source, x_mm, y_mm, confidence))
            self._append_event(active)
            return self._after_change(active)

    def next_turn(self, source: str = "manual") -> dict[str, Any]:
        with self._lock:
            active = self._require_active()
            self._check_bot(active, source)
            active.game.next_turn()
            active.meta.append(EventMeta(source))
            self._append_event(active)
            state = self._after_change(active)
            self._notify("next")
            return state

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

    def correct(
        self, turn_index: int, dart_index: int, dart: Dart, bounce: bool = False
    ) -> dict[str, Any]:
        """Replaces a dart. ``bounce``: the dart hit the board where it was detected but fell
        out - it scores nothing, but the detection was right (kept as training data)."""
        with self._lock:
            active = self._require_active()
            if bounce:
                dart = Dart.miss()
            seq = active.game.replace_dart(turn_index, dart_index, dart)
            source = "bounce" if bounce else "corrected"
            with self._sessions() as session:
                record = session.scalars(
                    select(GameEventRecord).where(
                        GameEventRecord.game_id == active.id, GameEventRecord.seq == seq
                    )
                ).one()
                record.segment, record.multiplier = dart.segment, dart.multiplier
                record.source = source
                active.meta[seq].source = source
                session.commit()
            return self._after_change(active)

    def correct_event(self, seq: int, dart: Dart) -> dict[str, Any]:
        """Replaces the dart with event number ``seq`` of the current game (e.g. after the
        referee looked at it); unlike ``correct`` it can reach any leg."""
        with self._lock:
            active = self._require_active()
            game = active.game
            if not 0 <= seq < len(game.events) or not isinstance(game.events[seq], DartEvent):
                raise GameError("no_such_dart", "No dart with this number")
            backup = list(game.events)
            game.events[seq] = DartEvent(dart)
            try:
                game._replay()
            except GameError:
                game.events = backup
                game._replay()
                raise
            with self._sessions() as session:
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
                refs = [
                    PlayerRef(
                        gp.player_id,
                        None if gp.bot_level else gp.guest_name,
                        gp.bot_level,
                        gp.bot_of,
                    )
                    for gp in last.players
                ]
                mode, settings = last.mode, dict(last.settings)
            teams = teams_of(settings)
            if teams:
                settings["teams"] = teams[1:] + teams[:1]  # the next team starts
            else:
                refs = refs[1:] + refs[:1]
            return self.create(mode, settings, refs, abort_active=True)

    def visits(self, game_id: int) -> list[dict[str, Any]]:
        """Every turn of a game with the event seq of each thrown dart (None for darts filled
        in by "next"), so the recorded camera images can be found."""
        with self._sessions() as session:
            record = session.get(GameRecord, game_id)
            if record is None:
                raise GameError("game_not_found", f"Game {game_id} not found")
            game = create_game(
                record.mode, engine_players(record.settings, len(record.players)), record.settings
            )
            seqs: dict[int, list[int | None]] = {}  # id(turn) -> event seqs
            for event in record.events:
                parsed = _event_from_record(event)
                if not isinstance(parsed, DartEvent):
                    game.next_turn()
                    continue
                legs_before = len(game.legs)
                game.throw(parsed.dart)
                # a winning dart starts the next leg: its turn is in the previous one
                leg = game.legs[legs_before - 1] if len(game.legs) > legs_before else game.legs[-1]
                turn = leg.turns[-1]
                seqs.setdefault(id(turn), []).append(event.seq)
            result = []
            for leg in game.legs:
                for index, turn in enumerate(leg.turns):
                    thrown = seqs.get(id(turn), [])
                    result.append(
                        {
                            "set": leg.set_number,
                            "leg": leg.number,
                            "turn_index": index,
                            "player": turn.player,
                            "darts": [d.label for d in turn.darts],
                            # implicit misses come last and have no event
                            "seqs": thrown + [None] * (len(turn.darts) - len(thrown)),
                            "total": turn.total,
                            "bust": turn.bust,
                        }
                    )
            return result

    def play_on(self, legs_to_win: int, sets_to_win: int) -> dict[str, Any]:
        """Continues the last finished X01/Cricket match with a higher target (e.g. first to 3
        legs becomes first to 4). Games are event lists, so the match is simply replayed with
        the new target and becomes active again."""
        with self._lock:
            if self._active is not None and not self._active.game.finished:
                raise GameError("game_active", "Another game is still running")
            with self._sessions() as session:
                record = session.scalars(
                    select(GameRecord).order_by(GameRecord.id.desc()).limit(1)
                ).first()
                if record is None or record.status != "finished":
                    raise GameError("no_game", "There is no finished game to continue")
                if record.mode not in ("x01", "cricket"):
                    raise GameError("play_on_mode", "Only X01 and Cricket matches can continue")
                old = record.settings
                if (legs_to_win, sets_to_win) <= (old["legs_to_win"], old["sets_to_win"]) or (
                    legs_to_win < old["legs_to_win"] or sets_to_win < old["sets_to_win"]
                ):
                    raise GameError("invalid_settings", "The new target must be higher")
                settings = {**old, "legs_to_win": legs_to_win, "sets_to_win": sets_to_win}
                events = [_event_from_record(e) for e in record.events]
                game = replay_game(
                    record.mode, engine_players(settings, len(record.players)), settings, events
                )
                if game.finished:
                    raise GameError("invalid_settings", "The match would already be decided")
                record.settings = game.settings_dict()
                record.status, record.finished_at, record.winner_position = "active", None, None
                session.commit()
                self._active = ActiveGame(
                    id=record.id,
                    settings=dict(record.settings),
                    game=game,
                    players=[_player_info(gp) for gp in record.players],
                    created_at=record.created_at.isoformat(),
                    meta=[EventMeta(e.source, e.x_mm, e.y_mm, e.confidence) for e in record.events],
                )
            log.info("game_continued", game_id=record.id, legs=legs_to_win, sets=sets_to_win)
            self._notify("new_game")
            return self._after_change(self._active)

    def bot_turn(self) -> tuple[int, Game, int, int | None] | None:
        """(game id, game, bot level, imitated player) while a bot is in control of the board,
        else None."""
        with self._lock:
            active = self._active
            if active is None:
                return None
            owner = self._turn_owner(active)
            if owner is None or not active.players[owner].get("bot_level"):
                return None
            info = active.players[owner]
            return active.id, active.game, int(info["bot_level"]), info.get("bot_of")

    # --- internals ----------------------------------------------------------------------

    @staticmethod
    def _turn_owner(active: ActiveGame) -> int | None:
        """Who has to act next: the thrower, or whoever has to pull their darts."""
        game = active.game
        if game.finished:
            return None
        state = game.state()
        if state["leg_winner"] is not None:
            return int(state["leg_winner"])
        return game.current_player

    def _check_bot(self, active: ActiveGame, source: str) -> None:
        # the camera must not score a bot's turn (e.g. the player pulling their darts)
        owner = self._turn_owner(active)
        if source == "auto" and owner is not None and active.players[owner].get("bot_level"):
            raise GameError("bot_turn", "A bot is throwing")

    def _require_active(self) -> ActiveGame:
        if self._active is None:
            raise GameError("no_active_game", "No game is running")
        return self._active

    def _load(self, session: Session, game_id: int) -> ActiveGame:
        record = session.get(GameRecord, game_id)
        if record is None:
            raise GameError("game_not_found", f"Game {game_id} not found")
        events = [_event_from_record(e) for e in record.events]
        game = replay_game(
            record.mode,
            engine_players(record.settings, len(record.players)),
            record.settings,
            events,
        )
        return ActiveGame(
            id=record.id,
            settings=dict(record.settings),
            game=game,
            players=[_player_info(gp) for gp in record.players],
            created_at=record.created_at.isoformat(),
            meta=[EventMeta(e.source, e.x_mm, e.y_mm, e.confidence) for e in record.events],
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
                confidence=meta.confidence,
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
                gp.stats = self._member_stats(active, stats, gp.position)
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
        self._notify("change")
        return state or {}

    def _turn_meta(self, active: ActiveGame) -> list[EventMeta]:
        game = active.game
        turn = game.state()["turn"]
        if not turn:
            return []
        count = len(turn["darts"])
        # darts of the shown turn are the last dart events (implicit misses have no event)
        dart_meta = [
            m for m, e in zip(active.meta, game.events, strict=True) if isinstance(e, DartEvent)
        ]
        return dart_meta[-count:] if count else []

    @staticmethod
    def _team_of(active: ActiveGame, position: int) -> int | None:
        teams = teams_of(active.settings)
        if not teams:
            return None
        return next(t for t, members in enumerate(teams) if position in members)

    def _member_stats(self, active: ActiveGame, stats: list[Any], position: int) -> dict[str, Any]:
        team = self._team_of(active, position)
        if team is None:
            return dict(stats[position].to_dict())
        return dict(stats[team].to_dict()) | {"team_game": True}

    def _display_players(self, active: ActiveGame, stats: list[Any]) -> list[dict[str, Any]]:
        """The players as the scoreboard shows them: in team games one entry per team."""
        teams = teams_of(active.settings)
        if not teams:
            return [{**info, "stats": stats[info["position"]].to_dict()} for info in active.players]
        result = []
        for t, members in enumerate(teams):
            infos = [active.players[m] for m in members]
            result.append(
                {
                    "position": t,
                    "player_id": None,
                    "name": " & ".join(i["name"] for i in infos),
                    "color": infos[0]["color"],
                    "avatar": None,
                    "guest": False,
                    "bot_level": None,
                    "bot_of": None,
                    "members": infos,
                    "stats": stats[t].to_dict(),
                }
            )
        return result

    def _thrower(self, active: ActiveGame) -> dict[str, Any] | None:
        teams = teams_of(active.settings)
        if not teams or active.game.finished:
            return None
        member = current_member(active.game, teams)
        return {"team": active.game.current_player, **active.players[member]}

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
            "event_count": len(game.events),
            # how each dart of the shown turn was entered: manual | auto | corrected
            "turn_sources": [m.source for m in self._turn_meta(active)],
            # confidence of automatically detected darts of the shown turn (None if manual)
            "turn_confidence": [m.confidence for m in self._turn_meta(active)],
            # board positions (mm) of the shown turn's darts, None where unknown
            "turn_positions": [
                [m.x_mm, m.y_mm] if m.x_mm is not None and m.y_mm is not None else None
                for m in self._turn_meta(active)
            ],
            "players": self._display_players(active, stats),
            # team games: who of the team at the board throws
            "thrower": self._thrower(active),
            # the leg the history belongs to (the finished one until the darts are pulled)
            "history_leg": {"set": leg.set_number, "leg": leg.number},
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
