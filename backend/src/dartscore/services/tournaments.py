"""Local tournaments: knockout brackets (with byes) and round robins on one board.

A match is a dict {"id", "round", "slot", "a", "b", "game_id", "winner", "bye"}; "a"/"b"
are indices into the tournament's entries (None = not decided yet, or no opponent). Each
match is played as an ordinary game, so all statistics keep working.
"""

import math
import random
import threading
from collections.abc import Callable
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dartscore.game import GameError
from dartscore.services.games import BOT_MODES, GameService, PlayerRef
from dartscore.storage.models import GameRecord, Player, Tournament

log = structlog.get_logger(__name__)

FORMATS = ("knockout", "round_robin")
MAX_ENTRIES = 16


def _seed_order(size: int) -> list[int]:
    """Standard bracket order of seeds 0..size-1 so the top seeds meet last."""
    order = [0]
    while len(order) < size:
        n = len(order) * 2
        order = [x for s in order for x in (s, n - 1 - s)]
    return order


def knockout_matches(entries: int) -> list[dict[str, Any]]:
    size = 2 ** math.ceil(math.log2(max(2, entries)))
    order = _seed_order(size)
    matches: list[dict[str, Any]] = []
    rounds = int(math.log2(size))
    for r in range(1, rounds + 1):
        for slot in range(size >> r):
            matches.append(
                {"id": len(matches), "round": r, "slot": slot, "a": None, "b": None,
                 "game_id": None, "winner": None, "bye": False}
            )  # fmt: skip
    for slot in range(size // 2):
        a, b = order[2 * slot], order[2 * slot + 1]
        match = matches[slot]
        match["a"] = a if a < entries else None
        match["b"] = b if b < entries else None
    # a first-round match without an opponent is a bye
    for match in matches[: size // 2]:
        if (match["a"] is None) != (match["b"] is None):
            match["bye"] = True
            _set_winner(matches, match, match["a"] if match["a"] is not None else match["b"])
    return matches


def round_robin_matches(entries: int) -> list[dict[str, Any]]:
    """Circle method: everybody meets everybody once, spread over rounds."""
    players: list[int | None] = list(range(entries))
    if entries % 2:
        players.append(None)
    n = len(players)
    matches: list[dict[str, Any]] = []
    for r in range(n - 1):
        for i in range(n // 2):
            a, b = players[i], players[n - 1 - i]
            if a is not None and b is not None:
                matches.append(
                    {"id": len(matches), "round": r + 1, "slot": i, "a": a, "b": b,
                     "game_id": None, "winner": None, "bye": False}
                )  # fmt: skip
        players = [players[0], players[-1], *players[1:-1]]
    return matches


def _set_winner(matches: list[dict[str, Any]], match: dict[str, Any], winner: int) -> None:
    """Records a knockout result and moves the winner into the next round."""
    match["winner"] = winner
    following = [
        m for m in matches if m["round"] == match["round"] + 1 and m["slot"] == match["slot"] // 2
    ]
    if following:
        following[0]["a" if match["slot"] % 2 == 0 else "b"] = winner


def standings(tournament: Tournament, legs: dict[int, tuple[int, int]]) -> list[dict[str, Any]]:
    """Round-robin table: wins, then leg difference. ``legs`` maps game id -> (legs a, legs b)."""
    rows = {
        i: {"entry": i, "played": 0, "won": 0, "legs_for": 0, "legs_against": 0}
        for i in range(len(tournament.entries))
    }
    for match in tournament.matches:
        if match["winner"] is None or match["bye"]:
            continue
        a, b = match["a"], match["b"]
        la, lb = legs.get(match["game_id"], (0, 0))
        for me, lf, la_ in ((a, la, lb), (b, lb, la)):
            row = rows[me]
            row["played"] += 1
            row["won"] += int(match["winner"] == me)
            row["legs_for"] += lf
            row["legs_against"] += la_
    return sorted(
        rows.values(), key=lambda r: (-r["won"], r["legs_against"] - r["legs_for"], r["entry"])
    )


class TournamentService:
    def __init__(self, sessions: sessionmaker[Session], games: GameService) -> None:
        self._sessions = sessions
        self._games = games
        self._lock = threading.Lock()
        self.on_change: Callable[[], None] | None = None
        games.add_listener(self._on_game_event)

    # --- queries --------------------------------------------------------------------

    def overview(self) -> list[dict[str, Any]]:
        with self._sessions() as session:
            rows = session.scalars(select(Tournament).order_by(Tournament.id.desc())).all()
            return [self._summary(t) for t in rows]

    def get(self, tournament_id: int) -> dict[str, Any]:
        with self._sessions() as session:
            tournament = self._load(session, tournament_id)
            return self._detail(session, tournament)

    def for_game(self, game_id: int) -> dict[str, Any] | None:
        with self._sessions() as session:
            for tournament in session.scalars(select(Tournament)):
                if any(m["game_id"] == game_id for m in tournament.matches):
                    return self._summary(tournament)
        return None

    # --- commands -------------------------------------------------------------------

    def create(
        self,
        name: str,
        fmt: str,
        mode: str,
        settings: dict[str, Any],
        entries: list[dict[str, Any]],
        shuffle: bool,
    ) -> dict[str, Any]:
        if fmt not in FORMATS:
            raise GameError("invalid_settings", f"format must be one of {FORMATS}")
        if mode not in BOT_MODES:
            raise GameError("invalid_settings", "Tournaments are played in X01 or Cricket")
        if not 2 <= len(entries) <= MAX_ENTRIES:
            raise GameError("invalid_settings", f"A tournament needs 2-{MAX_ENTRIES} players")
        entries = list(entries)
        if shuffle:
            random.shuffle(entries)
        matches = (
            knockout_matches(len(entries))
            if fmt == "knockout"
            else round_robin_matches(len(entries))
        )
        with self._sessions() as session:
            for entry in entries:
                if (
                    entry.get("player_id") is not None
                    and session.get(Player, entry["player_id"]) is None
                ):
                    raise GameError("player_not_found", f"Player {entry['player_id']} not found")
            tournament = Tournament(
                name=" ".join(name.split())[:60] or "Tournament",
                format=fmt,
                mode=mode,
                settings=settings,
                entries=entries,
                matches=matches,
                status="active",
            )
            session.add(tournament)
            session.commit()
            log.info("tournament_created", id=tournament.id, format=fmt, entries=len(entries))
            return self._detail(session, tournament)

    def start_match(self, tournament_id: int, match_id: int) -> dict[str, Any]:
        """Starts the match as the active game."""
        with self._lock, self._sessions() as session:
            tournament = self._load(session, tournament_id)
            match = self._match(tournament, match_id)
            if match["winner"] is not None or match["a"] is None or match["b"] is None:
                raise GameError("invalid_settings", "This match cannot be played")
            refs = [
                self._ref(tournament.entries[match["a"]]),
                self._ref(tournament.entries[match["b"]]),
            ]
            state = self._games.create(tournament.mode, dict(tournament.settings), refs)
            matches = [dict(m) for m in tournament.matches]
            matches[match_id]["game_id"] = state["id"]
            tournament.matches = matches
            session.commit()
            return state

    def delete(self, tournament_id: int) -> None:
        with self._sessions() as session:
            session.delete(self._load(session, tournament_id))
            session.commit()

    # --- internals ------------------------------------------------------------------

    def _on_game_event(self, event: str) -> None:
        if event != "change":
            return
        state = self._games.active_state()
        if not state or not state.get("finished") or state.get("winner") is None:
            return
        try:
            self._record(int(state["id"]), int(state["winner"]))
        except Exception:
            log.exception("tournament_result_failed")

    def _record(self, game_id: int, winner_position: int) -> None:
        with self._lock, self._sessions() as session:
            for tournament in session.scalars(
                select(Tournament).where(Tournament.status == "active")
            ):
                matches = [dict(m) for m in tournament.matches]
                match = next((m for m in matches if m["game_id"] == game_id), None)
                if match is None or match["winner"] is not None:
                    continue
                winner = match["a"] if winner_position == 0 else match["b"]
                if tournament.format == "knockout":
                    _set_winner(matches, match, winner)
                else:
                    match["winner"] = winner
                tournament.matches = matches
                if all(m["winner"] is not None for m in matches):
                    tournament.status = "finished"
                session.commit()
                log.info("tournament_result", id=tournament.id, match=match["id"], winner=winner)
                if self.on_change:
                    self.on_change()

    @staticmethod
    def _ref(entry: dict[str, Any]) -> PlayerRef:
        return PlayerRef(entry.get("player_id"), entry.get("guest_name"))

    @staticmethod
    def _match(tournament: Tournament, match_id: int) -> dict[str, Any]:
        if not 0 <= match_id < len(tournament.matches):
            raise GameError("invalid_settings", "No such match")
        return dict(tournament.matches[match_id])

    @staticmethod
    def _load(session: Session, tournament_id: int) -> Tournament:
        tournament = session.get(Tournament, tournament_id)
        if tournament is None:
            raise GameError("tournament_not_found", f"Tournament {tournament_id} not found")
        return tournament

    def _names(self, session: Session, tournament: Tournament) -> list[dict[str, Any]]:
        result = []
        for entry in tournament.entries:
            player = session.get(Player, entry["player_id"]) if entry.get("player_id") else None
            result.append(
                {
                    "player_id": player.id if player else None,
                    "name": player.name if player else entry.get("guest_name") or "?",
                    "color": player.color if player else "#9e9e9e",
                }
            )
        return result

    def _summary(self, tournament: Tournament) -> dict[str, Any]:
        champion = None
        if tournament.status == "finished" and tournament.format == "knockout":
            champion = max(tournament.matches, key=lambda m: m["round"])["winner"]
        return {
            "id": tournament.id,
            "name": tournament.name,
            "format": tournament.format,
            "mode": tournament.mode,
            "status": tournament.status,
            "entries": len(tournament.entries),
            "created_at": tournament.created_at.isoformat(),
            "champion": champion,
        }

    def _detail(self, session: Session, tournament: Tournament) -> dict[str, Any]:
        legs: dict[int, tuple[int, int]] = {}
        for match in tournament.matches:
            if match["game_id"] is None:
                continue
            record = session.get(GameRecord, match["game_id"])
            if record is not None:
                won = [int((gp.stats or {}).get("legs_won", 0)) for gp in record.players]
                if len(won) == 2:
                    legs[match["game_id"]] = (won[0], won[1])
        detail = self._summary(tournament)
        detail.update(
            settings=tournament.settings,
            players=self._names(session, tournament),
            matches=[
                m | {"legs": legs.get(m["game_id"]) if m["game_id"] else None}
                for m in tournament.matches
            ],
            standings=standings(tournament, legs) if tournament.format == "round_robin" else None,
        )
        return detail
