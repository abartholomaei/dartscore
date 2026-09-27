"""training plans

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-27 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "training_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("plan", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_plans_player_id", "training_plans", ["player_id"])


def downgrade() -> None:
    op.drop_index("ix_training_plans_player_id", table_name="training_plans")
    op.drop_table("training_plans")
