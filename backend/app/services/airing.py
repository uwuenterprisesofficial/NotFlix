"""What airs when, from AniList's airing schedule (public, keyed by MAL id through idMal).

- The release calendar: every episode airing in a week, stored in `airing_schedule` and
  refreshed at most hourly (past weeks daily). Shows not in the catalogue yet are added with
  AniList's data and completed by the catalogue worker.
- How many episodes of a show have aired, so episodes that haven't aren't looked for on the
  streaming sites (`aired_episodes`).
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import redis
from app.db.session import AsyncSessionLocal
from app.models import AiringEpisode, Anime
from app.services import anilist_account, catalog_jobs

log = logging.getLogger(__name__)

PER_PAGE = 50
MAX_PAGES = 12  # a week is usually 150-300 episodes
WEEK_TTL_S = 3600
PAST_WEEK_TTL_S = 24 * 3600
SHOW_TTL = timedelta(hours=3)
LOCK_TTL_S = 120

_MEDIA = anilist_account.MEDIA_FIELDS + " isAdult "

SCHEDULE_QUERY = f"""
query ($page: Int, $start: Int, $end: Int) {{
  Page(page: $page, perPage: {PER_PAGE}) {{
    pageInfo {{ hasNextPage }}
    airingSchedules(airingAt_greater: $start, airingAt_lesser: $end, sort: TIME) {{
      episode airingAt media {{ {_MEDIA} }}
    }}
  }}
}}
"""

SHOW_QUERY = """
query ($mal: Int) {
  Media(idMal: $mal, type: ANIME) { status episodes nextAiringEpisode { episode airingAt } }
}
"""

_refreshing: dict[str, asyncio.Task] = {}
_checking: dict[int, asyncio.Task] = {}  # shows being asked about, by MAL id
_background: set[asyncio.Task] = set()
CHECK_WAIT_S = 4  # longest a page waits for AniList
CHECK_FAILED_TTL_S = 600


def week_start(day: datetime) -> datetime:
    """Monday 00:00 UTC of the week containing `day`."""
    day = day.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=day.weekday())


async def fetch(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """AniList's schedule between two times: [{episode, airingAt, media}], MAL ids only."""
    found: list[dict[str, Any]] = []
    async with anilist_account.AniListClient() as client:
        for page in range(1, MAX_PAGES + 1):
            data = await client.query(
                SCHEDULE_QUERY,
                {"page": page, "start": int(start.timestamp()) - 1, "end": int(end.timestamp())},
            )
            block = data.get("Page") or {}
            found += [
                s
                for s in block.get("airingSchedules") or []
                if (s.get("media") or {}).get("idMal") and not s["media"].get("isAdult")
            ]
            if not (block.get("pageInfo") or {}).get("hasNextPage"):
                break
    return found


async def store(db: AsyncSession, start: datetime, end: datetime, found: list[dict]) -> None:
    """Replace the stored schedule between two times; add unknown shows to the catalogue."""
    await db.execute(
        delete(AiringEpisode).where(AiringEpisode.airing_at >= start, AiringEpisode.airing_at < end)
    )
    rows = {
        (s["media"]["idMal"], s["episode"]): {
            "anime_id": s["media"]["idMal"],
            "episode": s["episode"],
            "airing_at": datetime.fromtimestamp(s["airingAt"], UTC),
        }
        for s in found
    }
    if rows:
        stmt = insert(AiringEpisode).values(list(rows.values()))
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=[AiringEpisode.anime_id, AiringEpisode.episode],
                set_={"airing_at": stmt.excluded.airing_at},
            )
        )
    media = {s["media"]["idMal"]: s["media"] for s in found}
    known = set(await db.scalars(select(Anime.id).where(Anime.id.in_(list(media)))))
    from app.services.sync import insert_missing_anime

    new = [anilist_account.anime_row(m) for i, m in media.items() if i not in known]
    await insert_missing_anime(db, new)

    # Each show's next episode, for the "hasn't aired yet" checks.
    now = datetime.now(UTC)
    upcoming: dict[int, tuple[int, datetime]] = {}
    for (anime_id, episode), row in sorted(rows.items(), key=lambda kv: kv[1]["airing_at"]):
        if row["airing_at"] > now and anime_id not in upcoming:
            upcoming[anime_id] = (episode, row["airing_at"])
    for anime in await db.scalars(select(Anime).where(Anime.id.in_(list(upcoming)))):
        anime.next_episode, anime.next_episode_at = upcoming[anime.id]
        anime.airing_checked_at = now
    await db.commit()
    await catalog_jobs.enqueue([r["id"] for r in new])


async def _refresh_week(monday: datetime) -> None:
    end = monday + timedelta(days=7)
    try:
        found = await fetch(monday, end)
    except anilist_account.AniListError as e:
        log.warning("Airing schedule of %s: %s", monday.date(), e)
        return
    async with AsyncSessionLocal() as db:
        await store(db, monday, end, found)
    ttl = PAST_WEEK_TTL_S if end < datetime.now(UTC) else WEEK_TTL_S
    await redis().set(f"schedule:week:{monday.date()}", 1, ex=ttl)


async def ensure_week(monday: datetime, wait: bool = False) -> bool:
    """Refresh a week's schedule in the background when it's out of date. With `wait`, wait
    for it (e.g. nothing is stored yet). Returns whether a refresh is running."""
    key = monday.date().isoformat()
    if await redis().exists(f"schedule:week:{key}"):
        return False
    task = _refreshing.get(key)
    if task is None:
        if not await redis().set(f"schedule:lock:{key}", 1, ex=LOCK_TTL_S, nx=True):
            return True  # another process is on it
        task = asyncio.create_task(_refresh_week(monday))
        _refreshing[key] = task
        task.add_done_callback(lambda _: _refreshing.pop(key, None))
    if wait:
        try:
            await asyncio.wait_for(asyncio.shield(task), 25)
        except TimeoutError:
            return True
        return False
    return True


async def wait_idle() -> None:
    while _refreshing or _checking or _background:
        tasks = [*_refreshing.values(), *_checking.values(), *_background]
        await asyncio.gather(*tasks, return_exceptions=True)


@dataclass
class Airing:
    anime_id: int
    episode: int
    airing_at: datetime


async def between(db: AsyncSession, start: datetime, end: datetime) -> list[Airing]:
    rows = await db.scalars(
        select(AiringEpisode)
        .where(AiringEpisode.airing_at >= start, AiringEpisode.airing_at < end)
        .order_by(AiringEpisode.airing_at)
    )
    return [Airing(r.anime_id, r.episode, r.airing_at) for r in rows]


async def _check_show(db: AsyncSession, anime: Anime) -> None:
    """Ask AniList for the show's next episode (for shows not in a fetched week)."""
    async with anilist_account.AniListClient() as client:
        data = await client.query(SHOW_QUERY, {"mal": anime.id})
    media = data.get("Media") or {}
    nxt = media.get("nextAiringEpisode")
    anime.next_episode = nxt["episode"] if nxt else None
    anime.next_episode_at = datetime.fromtimestamp(nxt["airingAt"], UTC) if nxt else None
    anime.airing_checked_at = datetime.now(UTC)
    # MAL's status can lag behind the first broadcast.
    if media.get("status") == "NOT_YET_RELEASED":
        anime.status = "not_yet_aired"
    elif media.get("status") == "RELEASING":
        anime.status = "currently_airing"
    await db.commit()


async def _check_by_id(anime_id: int) -> None:
    async with AsyncSessionLocal() as db:
        anime = await db.get(Anime, anime_id)
        if anime is not None:
            await _check_show(db, anime)


async def _check(anime_id: int) -> None:
    """Ask AniList about a show once, however many requests want to know at the same time. A
    failure isn't retried for a while (every page view would wait for it otherwise)."""
    task = _checking.get(anime_id)
    if task is None:
        if await redis().exists(f"airing:failed:{anime_id}"):
            return
        task = asyncio.create_task(_check_by_id(anime_id))
        _checking[anime_id] = task
        task.add_done_callback(lambda _: _checking.pop(anime_id, None))
    try:
        await asyncio.shield(task)
    except anilist_account.AniListError as e:
        log.info("Next episode of anime %s unknown: %s", anime_id, e)
        await redis().set(f"airing:failed:{anime_id}", 1, ex=CHECK_FAILED_TTL_S)


async def aired_episodes(db: AsyncSession, anime: Anime | None) -> int | None:
    """How many episodes have aired; None when there's no limit to apply (finished, or not
    known). Episodes after that haven't aired, so there are no streams to look for.

    AniList is only waited for when the answer may be wrong otherwise (never checked, or the
    next episode's air time has passed); a check that's merely due runs in the background."""
    if anime is None or anime.status == "finished_airing":
        return None
    now = datetime.now(UTC)
    passed = anime.next_episode_at is not None and anime.next_episode_at <= now
    fresh = anime.airing_checked_at is not None and now - anime.airing_checked_at < SHOW_TTL
    if anime.airing_checked_at is None or passed:
        # Past the wait, it carries on in the background; this answer uses what's known.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(_check(anime.id), CHECK_WAIT_S)
        await db.refresh(anime)
    elif not fresh:
        task = asyncio.create_task(_check(anime.id))
        _background.add(task)
        task.add_done_callback(_background.discard)
    if anime.next_episode_at is not None and anime.next_episode_at > now and anime.next_episode:
        return anime.next_episode - 1
    return 0 if anime.status == "not_yet_aired" else None
