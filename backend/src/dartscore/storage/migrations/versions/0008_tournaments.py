"""tournaments

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-27 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tournaments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("matches", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("tournaments")
