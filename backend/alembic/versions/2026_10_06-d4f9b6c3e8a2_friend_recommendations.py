"""recommendations to friends

Revision ID: d4f9b6c3e8a2
Revises: c3e8a5b2d7f1
Create Date: 2026-10-06 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4f9b6c3e8a2"
down_revision: str | Sequence[str] | None = "c3e8a5b2d7f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "friend_recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_user_id", sa.Integer(), nullable=False),
        sa.Column("to_user_id", sa.Integer(), nullable=False),
        sa.Column("anime_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(["anime_id"], ["anime.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_user_id", "to_user_id", "anime_id"),
    )
    op.create_index(
        op.f("ix_friend_recommendations_from_user_id"),
        "friend_recommendations",
        ["from_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_friend_recommendations_to_user_id"),
        "friend_recommendations",
        ["to_user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_friend_recommendations_to_user_id"), table_name="friend_recommendations"
    )
    op.drop_index(
        op.f("ix_friend_recommendations_from_user_id"), table_name="friend_recommendations"
    )
    op.drop_table("friend_recommendations")
