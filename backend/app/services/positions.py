"""Resume watching: where the user stopped in the episode they're on, one per show."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlaybackPosition

MIN_POSITION_S = 15  # before this, there's nothing worth resuming
CREDITS_S = 120  # this close to the end the episode counts as finished


async def save(
    db: AsyncSession,
    user_id: int,
    anime_id: int,
    episode: int,
    position_s: float,
    duration_s: float | None,
) -> PlaybackPosition | None:
    """Remember the position (replacing the show's earlier episode). A position in the
    credits clears it: the episode is done. One in the first seconds changes nothing."""
    if duration_s and position_s >= duration_s - CREDITS_S:
        await clear(db, user_id, anime_id, episode)
        return None
    if position_s < MIN_POSITION_S:
        return await get(db, user_id, anime_id)
    values = {
        "user_id": user_id, "anime_id": anime_id, "episode": episode,
        "position_s": round(position_s, 1), "duration_s": duration_s,
        "updated_at": datetime.now(UTC),
    }  # fmt: skip
    stmt = insert(PlaybackPosition).values(values)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[PlaybackPosition.user_id, PlaybackPosition.anime_id],
            set_={k: stmt.excluded[k] for k in values if k not in ("user_id", "anime_id")},
        )
    )
    await db.commit()
    return await get(db, user_id, anime_id)


async def get(db: AsyncSession, user_id: int, anime_id: int) -> PlaybackPosition | None:
    return await db.scalar(
        select(PlaybackPosition).where(
            PlaybackPosition.user_id == user_id, PlaybackPosition.anime_id == anime_id
        )
    )


async def for_shows(db: AsyncSession, user_id: int, ids: list[int]) -> dict[int, PlaybackPosition]:
    rows = await db.scalars(
        select(PlaybackPosition).where(
            PlaybackPosition.user_id == user_id, PlaybackPosition.anime_id.in_(ids)
        )
    )
    return {p.anime_id: p for p in rows}


async def clear(
    db: AsyncSession, user_id: int, anime_id: int, up_to_episode: int | None = None
) -> None:
    """Forget the position (only if it's in `up_to_episode` or earlier, when given: e.g. the
    episode was marked watched)."""
    stmt = delete(PlaybackPosition).where(
        PlaybackPosition.user_id == user_id, PlaybackPosition.anime_id == anime_id
    )
    if up_to_episode is not None:
        stmt = stmt.where(PlaybackPosition.episode <= up_to_episode)
    await db.execute(stmt)
    await db.commit()
