"""community recommendations

Revision ID: e5a1c7d9b3f4
Revises: d4f9b6c3e8a2
Create Date: 2026-10-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5a1c7d9b3f4"
down_revision: str | Sequence[str] | None = "d4f9b6c3e8a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "community_recommendations",
        sa.Column("anime_id", sa.Integer(), nullable=False),
        sa.Column("recommended_id", sa.Integer(), nullable=False),
        sa.Column("votes", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("anime_id", "recommended_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("community_recommendations")
