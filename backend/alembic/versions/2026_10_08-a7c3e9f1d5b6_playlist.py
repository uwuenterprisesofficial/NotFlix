"""playlist

Revision ID: a7c3e9f1d5b6
Revises: f6b2d8e0c4a5
Create Date: 2026-10-08 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9f1d5b6"
down_revision: str | Sequence[str] | None = "f6b2d8e0c4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("playlist_auto_airing", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_table(
        "playlist_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("anime_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("auto", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("hidden_through", sa.Integer(), nullable=True),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["anime_id"], ["anime.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "anime_id"),
    )
    op.create_index(op.f("ix_playlist_items_user_id"), "playlist_items", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_playlist_items_user_id"), table_name="playlist_items")
    op.drop_table("playlist_items")
    op.drop_column("users", "playlist_auto_airing")
