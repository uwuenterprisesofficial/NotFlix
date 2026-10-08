"""What airs in a season: MAL's seasonal list (cached; the shows go into the catalogue), and the
catalogue's own shows of that season."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_json, redis, set_json
from app.models import Anime
from app.services import catalog, catalog_jobs, library, mal
from app.services.sync import upsert_anime

log = logging.getLogger(__name__)

SEASONS = ("winter", "spring", "summer", "fall")
CURRENT_TTL_S = 6 * 3600  # this season and the next ones change while they air
PAST_TTL_S = 7 * 24 * 3600
FAILURE_TTL_S = 300
SKIPPED_TYPES = {"music", "pv", "cm"}


def of(day: datetime) -> tuple[int, str]:
    return day.year, SEASONS[(day.month - 1) // 3]


def current() -> tuple[int, str]:
    return of(datetime.now(UTC))


def step(year: int, season: str, by: int) -> tuple[int, str]:
    index = year * 4 + SEASONS.index(season) + by
    return index // 4, SEASONS[index % 4]


async def _from_mal(db: AsyncSession, year: int, season: str) -> list[int] | None:
    """MAL's seasonal list (ids), cached; None when MAL isn't there or can't answer."""
    if not catalog.mal_configured() or library.upstream() is not None:
        return None
    key = f"mal:season:{year}:{season}"
    ids = await get_json(key)
    if ids is not None:
        return ids
    if await redis().exists(f"{key}:failed"):
        return None
    try:
        async with mal.MalClient() as client:
            nodes = await client.season(year, season)
    except mal.MalError as e:
        log.info("MAL season %s %s: %s", season, year, e)
        await redis().set(f"{key}:failed", 1, ex=FAILURE_TTL_S)
        return None
    await upsert_anime(db, nodes)
    await db.commit()
    ids = [n["id"] for n in nodes]
    past = step(year, season, 1) < current()
    await set_json(key, ids, PAST_TTL_S if past else CURRENT_TTL_S)
    return ids


async def shows(db: AsyncSession, year: int, season: str) -> tuple[list[Anime], bool]:
    """The season's shows, the most popular first, and whether MAL's list is part of it (else
    only the catalogue's shows of that season are known)."""
    ids = await _from_mal(db, year, season)
    found = await catalog.anime_by_ids(db, ids) if ids else []
    known = {a.id for a in found}
    local = await db.scalars(
        select(Anime)
        .where(Anime.start_season == f"{season} {year}")
        .order_by(Anime.num_list_users.desc().nulls_last(), Anime.id)
    )
    found += [a for a in local if a.id not in known]
    found = [a for a in found if (a.media_type or "") not in SKIPPED_TYPES]
    found.sort(key=lambda a: -(a.num_list_users or 0))
    await catalog_jobs.complete(found)
    return found, ids is not None
