from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, OptionalUser
from app.models import ListEntry
from app.schemas import AiringOut, AnimeCard, CalendarOut
from app.services import airing, catalog
from app.services.taste import predictor_for

router = APIRouter(tags=["calendar"])

MAX_RANGE = timedelta(days=8)


async def cards(db: DB, user, episodes: list[airing.Airing]) -> list[AnimeCard]:
    """A card per episode (with its air time), for the shows the catalogue has."""
    ids = list(dict.fromkeys(e.anime_id for e in episodes))
    shows = {a.id: a for a in await catalog.anime_by_ids(db, ids)}
    entries: dict[int, ListEntry] = {}
    if user is not None and ids:
        rows = await db.scalars(
            select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id.in_(ids))
        )
        entries = {e.anime_id: e for e in rows}
    predictor = await predictor_for(db, user)
    out = []
    for e in episodes:
        if e.anime_id not in shows:
            continue
        card = catalog.to_card(shows[e.anime_id], entries.get(e.anime_id), predictor=predictor)
        card.airing = AiringOut(episode=e.episode, airing_at=e.airing_at)
        out.append(card)
    return out


@router.get("/calendar", response_model=CalendarOut)
async def calendar(
    user: OptionalUser,
    db: DB,
    start: datetime,
    end: datetime,
):
    """The release calendar between two ISO times (e.g. local midnights; at most 8 days).
    The schedule is refreshed in the background when it's older than an hour; the first time
    it's waited for."""
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if not start < end <= start + MAX_RANGE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "At most 8 days")
    refreshing = False
    monday = airing.week_start(start)
    while monday < end:
        have = await airing.between(db, monday, monday + timedelta(days=7))
        refreshing |= await airing.ensure_week(monday, wait=not have)
        monday += timedelta(days=7)
    episodes = await airing.between(db, start, end)
    return CalendarOut(items=await cards(db, user, episodes), refreshing=refreshing)
