"""Database tables (SQLAlchemy ORM)."""

from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSON}


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    color: Mapped[str] = mapped_column(String(7), default="#1e88e5")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    # archived players keep their statistics but are hidden from selection
    archived_at: Mapped[datetime | None] = mapped_column(default=None)
    # preferences: finishing double for checkout suggestions (1-20, 25 = bull), throwing hand,
    # game mode preselected when this player starts a game
    favorite_double: Mapped[int | None] = mapped_column(default=None)
    throwing_hand: Mapped[str | None] = mapped_column(String(5), default=None)
    default_mode: Mapped[str | None] = mapped_column(String(20), default=None)
    # optional PIN against accidental edits (not a security feature): "salt$scrypt-hash"
    pin_hash: Mapped[str | None] = mapped_column(String(128), default=None)
    # profile picture: "photo:<version>" (file in data/avatars) or "gallery:<name>"
    avatar: Mapped[str | None] = mapped_column(String(40), default=None)


class GameRecord(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(20))
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # active | finished | aborted
    status: Mapped[str] = mapped_column(String(10), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    # position of the winning player in game_players
    winner_position: Mapped[int | None] = mapped_column(default=None)

    players: Mapped[list["GamePlayer"]] = relationship(
        back_populates="game", order_by="GamePlayer.position", cascade="all, delete-orphan"
    )
    events: Mapped[list["GameEventRecord"]] = relationship(
        back_populates="game", order_by="GameEventRecord.seq", cascade="all, delete-orphan"
    )


class GamePlayer(Base):
    __tablename__ = "game_players"
    __table_args__ = (UniqueConstraint("game_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]
    # None for guests
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), index=True)
    guest_name: Mapped[str | None] = mapped_column(String(40))
    # computer opponent: its target 3-dart average (guest_name holds its display name)
    bot_level: Mapped[int | None] = mapped_column(default=None)
    # a personal bot: the player whose throwing it imitates
    bot_of: Mapped[int | None] = mapped_column(default=None)
    # a bot's profile picture ("gallery:<name>"), picked when the game starts
    avatar: Mapped[str | None] = mapped_column(String(40), default=None)
    # statistics of this player in this game (see game.stats), updated on every change
    stats: Mapped[dict[str, Any] | None] = mapped_column(default=None)

    game: Mapped[GameRecord] = relationship(back_populates="players")
    player: Mapped[Player | None] = relationship()


class GameEventRecord(Base):
    __tablename__ = "game_events"
    __table_args__ = (UniqueConstraint("game_id", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int]
    # dart | next
    kind: Mapped[str] = mapped_column(String(10))
    segment: Mapped[int | None]
    multiplier: Mapped[int | None]
    # board position if the dart was detected by the cameras
    x_mm: Mapped[float | None]
    y_mm: Mapped[float | None]
    # manual | auto | corrected | bounce
    source: Mapped[str] = mapped_column(String(10), default="manual")
    # confidence of an automatic detection (0..1)
    confidence: Mapped[float | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    game: Mapped[GameRecord] = relationship(back_populates="events")


class Tournament(Base):
    """A local tournament on the one board; matches are stored as JSON (see
    services.tournaments), each played as a normal game."""

    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    # knockout | round_robin
    format: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(20))
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # [{"player_id": 1} | {"guest_name": "Tom"}] in seeding order
    entries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    matches: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # active | finished
    status: Mapped[str] = mapped_column(String(10), default="active")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class TrainingPlanRecord(Base):
    """A player working through a training plan (see services.training_plans)."""

    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    # key of the built-in plan
    plan: Mapped[str] = mapped_column(String(40))
    # active | finished | stopped
    status: Mapped[str] = mapped_column(String(10), default="active")
    # [{"session": 0, "drill": 1, "game_id": 12, "score": 34, "achieved": true}]
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
