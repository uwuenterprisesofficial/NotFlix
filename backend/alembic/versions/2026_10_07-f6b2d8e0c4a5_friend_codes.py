"""friend codes

Revision ID: f6b2d8e0c4a5
Revises: e5a1c7d9b3f4
Create Date: 2026-10-07 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6b2d8e0c4a5"
down_revision: str | Sequence[str] | None = "e5a1c7d9b3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("friend_code", sa.String(length=16), nullable=True))
    op.create_unique_constraint("uq_users_friend_code", "users", ["friend_code"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_users_friend_code", "users", type_="unique")
    op.drop_column("users", "friend_code")
