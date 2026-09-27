"""Local player profiles."""

import hashlib
import hmac
import secrets

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


def _hash_pin(pin: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{salt.hex()}${digest.hex()}"


def check_pin(player: Player, pin: str | None) -> None:
    """Raises unless the player has no PIN or ``pin`` matches it."""
    if player.pin_hash is None:
        return
    if pin is None:
        raise GameError("pin_required", "This profile is protected by a PIN")
    salt, _ = player.pin_hash.split("$", 1)
    if not hmac.compare_digest(_hash_pin(pin, bytes.fromhex(salt)), player.pin_hash):
        raise GameError("wrong_pin", "Wrong PIN")


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

    def update(
        self,
        player_id: int,
        name: str | None = None,
        color: str | None = None,
        preferences: dict[str, object] | None = None,
        pin: str | None = None,
        new_pin: str | bool | None = False,
    ) -> Player:
        """``preferences``: favorite_double, throwing_hand, default_mode (None clears one).
        ``pin``: the current PIN, if the profile has one. ``new_pin``: a PIN to set, None to
        remove it, False to leave it."""
        with self._sessions() as session:
            player = session.get(Player, player_id)
            if player is None:
                raise GameError("player_not_found", f"Player {player_id} not found")
            check_pin(player, pin)
            if new_pin is not False:
                player.pin_hash = _hash_pin(new_pin) if isinstance(new_pin, str) else None
            if name is not None:
                player.name = self._check_name(session, name, exclude_id=player_id)
            if color is not None:
                player.color = color
            for key, value in (preferences or {}).items():
                if key not in ("favorite_double", "throwing_hand", "default_mode"):
                    raise GameError("invalid_settings", f"Unknown preference {key}")
                setattr(player, key, value)
            session.commit()
            return player

    def set_avatar(self, player_id: int, avatar: str | None, pin: str | None = None) -> Player:
        with self._sessions() as session:
            player = session.get(Player, player_id)
            if player is None:
                raise GameError("player_not_found", f"Player {player_id} not found")
            check_pin(player, pin)
            player.avatar = avatar
            session.commit()
            return player

    def delete(self, player_id: int, pin: str | None = None) -> bool:
        """Deletes a player without games; players with games are archived so their
        statistics survive. Returns True if the player was deleted, False if archived."""
        with self._sessions() as session:
            player = session.get(Player, player_id)
            if player is None:
                raise GameError("player_not_found", f"Player {player_id} not found")
            check_pin(player, pin)
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
