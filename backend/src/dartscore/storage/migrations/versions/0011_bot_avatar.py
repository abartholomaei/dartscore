"""bots wear a gallery picture

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-28 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("game_players", schema=None) as batch_op:
        batch_op.add_column(sa.Column("avatar", sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("game_players", schema=None) as batch_op:
        batch_op.drop_column("avatar")
