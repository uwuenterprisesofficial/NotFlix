"""shared stream library

Revision ID: c3e8a5b2d7f1
Revises: b7d2f4a1c9e0
Create Date: 2026-10-06 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e8a5b2d7f1"
down_revision: str | Sequence[str] | None = "b7d2f4a1c9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "shared_sources",
        sa.Column("anime_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("anime_id", "source", "episode"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("shared_sources")
