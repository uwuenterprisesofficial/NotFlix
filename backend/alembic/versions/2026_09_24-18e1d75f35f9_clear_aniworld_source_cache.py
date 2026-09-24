"""clear aniworld source cache

Revision ID: 18e1d75f35f9
Revises: d433df11cc55
Create Date: 2026-09-24 17:06:50.170458

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "18e1d75f35f9"
down_revision: str | Sequence[str] | None = "d433df11cc55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """AniWorld options change shape when switching to the AniWorld API; rescan them."""
    op.execute("DELETE FROM episode_sources WHERE provider = 'aniworld'")
    op.execute("DELETE FROM source_scans WHERE provider = 'aniworld'")


def downgrade() -> None:
    """Nothing to restore: the cache is rebuilt by the next scan."""
