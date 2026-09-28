"""gallery: the rabbit picture was replaced by a lion

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-28 17:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE players SET avatar = 'gallery:lion' WHERE avatar = 'gallery:rabbit'")


def downgrade() -> None:
    op.execute("UPDATE players SET avatar = 'gallery:rabbit' WHERE avatar = 'gallery:lion'")
