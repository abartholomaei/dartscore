"""bot players

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26 21:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("game_players", schema=None) as batch_op:
        batch_op.add_column(sa.Column("bot_level", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("game_players", schema=None) as batch_op:
        batch_op.drop_column("bot_level")
