"""index for shows with a dub

Revision ID: b7d2f4a1c9e0
Revises: 5e7efc42613c
Create Date: 2026-10-06 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d2f4a1c9e0"
down_revision: str | Sequence[str] | None = "5e7efc42613c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_episode_sources_language_anime",
        "episode_sources",
        ["language", "anime_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_episode_sources_language_anime", table_name="episode_sources")
