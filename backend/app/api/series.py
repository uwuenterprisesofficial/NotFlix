"""Progress in series without a MyAnimeList id (SerienStream series, which the desktop app finds
and plays on the user's PC). The backend only remembers the episode the user is on, for
Continue Watching on the home page."""

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import DB, CurrentUser
from app.models import SeriesProgress
from app.schemas import SeriesProgressIn, SeriesProgressOut

router = APIRouter(prefix="/series", tags=["series"])


@router.get("/progress", response_model=list[SeriesProgressOut])
async def list_progress(user: CurrentUser, db: DB):
    """The series the user is watching, the latest first."""
    rows = await db.scalars(
        select(SeriesProgress)
        .where(SeriesProgress.user_id == user.id)
        .order_by(SeriesProgress.updated_at.desc())
    )
    return list(rows)


# POST as well: navigator.sendBeacon can only POST.
@router.api_route("/{slug}/progress", methods=["PUT", "POST"], response_model=SeriesProgressOut)
async def save_progress(slug: str, body: SeriesProgressIn, user: CurrentUser, db: DB):
    """Remember the episode the user is on (replacing the series' earlier one)."""
    slug = slug.lower()
    values = {
        "user_id": user.id, "slug": slug, "title": body.title,
        "image_url": body.image_url, "season": body.season, "episode": body.episode,
        "updated_at": datetime.now(UTC),
    }  # fmt: skip
    stmt = insert(SeriesProgress).values(values)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[SeriesProgress.user_id, SeriesProgress.slug],
            set_={k: stmt.excluded[k] for k in values if k not in ("user_id", "slug")},
        )
    )
    await db.commit()
    return await db.scalar(
        select(SeriesProgress).where(SeriesProgress.user_id == user.id, SeriesProgress.slug == slug)
    )


@router.delete("/{slug}/progress", status_code=204)
async def clear_progress(slug: str, user: CurrentUser, db: DB) -> None:
    """Take the series off Continue Watching."""
    await db.execute(
        delete(SeriesProgress).where(
            SeriesProgress.user_id == user.id, SeriesProgress.slug == slug.lower()
        )
    )
    await db.commit()
