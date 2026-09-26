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
