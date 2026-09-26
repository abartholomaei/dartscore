"""Local player profiles."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from dartscore.game import GameError
from dartscore.storage.models import GamePlayer, Player, utcnow

DEFAULT_COLORS = (
    "#e53935",
    "#1e88e5",
    "#43a047",
    "#fb8c00",
    "#8e24aa",
    "#00acc1",
    "#fdd835",
    "#6d4c41",
)


class PlayerService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def list(self, include_archived: bool = False) -> list[Player]:
        with self._sessions() as session:
            query = select(Player).order_by(func.lower(Player.name))
            if not include_archived:
                query = query.where(Player.archived_at.is_(None))
            return list(session.scalars(query))

    def get(self, player_id: int) -> Player:
        with self._sessions() as session:
            player = session.get(Player, player_id)
            if player is None:
                raise GameError("player_not_found", f"Player {player_id} not found")
            return player

    def _check_name(self, session: Session, name: str, exclude_id: int | None = None) -> str:
        clean = " ".join(name.split())
        if not 1 <= len(clean) <= 40:
            raise GameError("invalid_name", "Name must be 1-40 characters")
        query = select(Player).where(
            func.lower(Player.name) == clean.lower(), Player.archived_at.is_(None)
        )
        if exclude_id is not None:
            query = query.where(Player.id != exclude_id)
        if session.scalars(query).first() is not None:
            raise GameError("name_taken", f"A player named {clean!r} already exists")
        return clean

    def create(self, name: str, color: str | None = None) -> Player:
        with self._sessions() as session:
            clean = self._check_name(session, name)
            if color is None:
                count = session.scalar(select(func.count(Player.id))) or 0
                color = DEFAULT_COLORS[count % len(DEFAULT_COLORS)]
            player = Player(name=clean, color=color)
            session.add(player)
            session.commit()
            return player

    def update(self, player_id: int, name: str | None = None, color: str | None = None) -> Player:
        with self._sessions() as session:
            player = session.get(Player, player_id)
            if player is None:
                raise GameError("player_not_found", f"Player {player_id} not found")
            if name is not None:
                player.name = self._check_name(session, name, exclude_id=player_id)
            if color is not None:
                player.color = color
            session.commit()
            return player

    def delete(self, player_id: int) -> bool:
        """Deletes a player without games; players with games are archived so their
        statistics survive. Returns True if the player was deleted, False if archived."""
        with self._sessions() as session:
            player = session.get(Player, player_id)
            if player is None:
                raise GameError("player_not_found", f"Player {player_id} not found")
            played = session.scalar(
                select(func.count(GamePlayer.id)).where(GamePlayer.player_id == player_id)
            )
            if played:
                player.archived_at = utcnow()
                session.commit()
                return False
            session.delete(player)
            session.commit()
            return True

    def restore(self, player_id: int) -> Player:
        with self._sessions() as session:
            player = session.get(Player, player_id)
            if player is None:
                raise GameError("player_not_found", f"Player {player_id} not found")
            self._check_name(session, player.name, exclude_id=player_id)
            player.archived_at = None
            session.commit()
            return player
