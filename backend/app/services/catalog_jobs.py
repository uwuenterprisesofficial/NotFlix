"""Handing shows to the catalogue worker (worker/catalog.py), which adds them to the database
and completes them: MAL's details and translated synopses. Pages never wait for it."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.cache import redis
from app.core.config import get_settings
from app.models import Anime

log = logging.getLogger(__name__)

# A show handed to the worker isn't handed over again for this long (it's queued or done).
QUEUED_TTL_S = 3600
AIRING_REFRESH = timedelta(days=1)
JOB_TIMEOUT_S = 30 * 60
JOB_SIZE = 25  # shows per job


def stale(anime: Anime) -> bool:
    """Whether the show's MAL data is due for a refresh (airing shows change more often)."""
    days = get_settings().catalog_refresh_days
    if anime.mal_details_at is None:
        return True
    if days <= 0:
        return False
    airing = anime.status in ("currently_airing", "not_yet_aired")
    limit = AIRING_REFRESH if airing else timedelta(days=days)
    return datetime.now(UTC) - anime.mal_details_at > limit


def incomplete(anime: Anime) -> bool:
    return anime.enriched_at is None or stale(anime)


def _enqueue_job(ids: list[int], rows: list[dict[str, Any]], refresh: bool) -> None:
    from app.worker.queue import catalog_queue

    catalog_queue().enqueue(
        "app.worker.catalog.enrich_catalog", ids, rows, refresh, job_timeout=JOB_TIMEOUT_S
    )


async def enqueue(
    ids: list[int], rows: list[dict[str, Any]] | None = None, refresh: bool = False
) -> list[int]:
    """Hand shows to the catalogue worker; `rows` are data already fetched for some of them
    (e.g. search results), stored as they are. Shows handed over within the last hour are
    skipped. Returns the ids actually queued. Never raises: the catalogue is best effort."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    try:
        pipe = redis().pipeline()
        for anime_id in ids:
            pipe.set(f"catalog:queued:{anime_id}", 1, ex=QUEUED_TTL_S, nx=True)
        fresh = [i for i, ok in zip(ids, await pipe.execute(), strict=True) if ok]
        for start in range(0, len(fresh), JOB_SIZE):
            chunk = fresh[start : start + JOB_SIZE]
            wanted = set(chunk)
            await asyncio.to_thread(
                _enqueue_job, chunk, [r for r in rows or [] if r["id"] in wanted], refresh
            )
        return fresh
    except Exception:
        log.warning("Could not queue %d show(s) for the catalogue", len(ids), exc_info=True)
        return []


async def complete(animes: list[Anime]) -> None:
    """Queue the shows whose catalogue entries aren't complete or are due for a refresh."""
    todo = [a.id for a in animes if incomplete(a)]
    await enqueue(todo, refresh=True)
