"""RQ entrypoint of the catalogue worker: store shows and complete their entries.

For each show: data handed over with the job is stored (MAL's is authoritative; another
source's only fills a gap), MAL's details are fetched when missing or due, and the synopsis in
every CATALOG_SYNOPSIS_LANGUAGES language is looked up (German: AniWorld, then AnimeToast).
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from app.core import cache
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, async_engine
from app.models import Anime
from app.services import catalog_jobs, mal, synopsis
from app.services.sync import insert_missing_anime, upsert_anime

log = logging.getLogger(__name__)

MAL_CONCURRENCY = 3
SYNOPSIS_CONCURRENCY = 2


def enrich_catalog(ids: list[int], rows: list[dict[str, Any]], refresh: bool = False) -> None:
    """RQ job (sync): run the async work on its own event loop."""
    asyncio.run(_job(ids, rows, refresh))


async def _job(ids: list[int], rows: list[dict[str, Any]], refresh: bool) -> None:
    try:
        await run(ids, rows, refresh)
    finally:
        # Pooled connections belong to this job's event loop.
        await async_engine.dispose()
        await cache.close()


def _languages() -> list[str]:
    raw = get_settings().catalog_synopsis_languages
    return [lang.strip() for lang in raw.split(",") if synopsis.supported(lang.strip())]


async def run(ids: list[int], rows: list[dict[str, Any]], refresh: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        mal_rows = [r for r in rows if r.get("mal_details_at")]
        other_rows = [r for r in rows if not r.get("mal_details_at")]
        if mal_rows:
            await upsert_anime(db, [], rows=mal_rows)
        if other_rows:
            await insert_missing_anime(db, other_rows)
        await db.commit()

        known = {a.id: a for a in await db.scalars(select(Anime).where(Anime.id.in_(ids)))}
        need_mal = [
            i for i in ids
            if i not in known or known[i].mal_details_at is None
            or (refresh and catalog_jobs.stale(known[i]))
        ]  # fmt: skip
        if need_mal and get_settings().mal_client_id:
            sem = asyncio.Semaphore(MAL_CONCURRENCY)

            async def fetch(anime_id: int) -> dict[str, Any] | None:
                async with sem:
                    try:
                        async with mal.MalClient() as client:
                            return await client.anime(anime_id)
                    except mal.MalError as e:
                        log.info("MAL details of anime %s: %s", anime_id, e)
                        return None

            nodes = [n for n in await asyncio.gather(*(fetch(i) for i in need_mal)) if n]
            if nodes:
                await upsert_anime(db, nodes)
                await db.commit()

        animes = list(await db.scalars(select(Anime).where(Anime.id.in_(ids))))
        sem = asyncio.Semaphore(SYNOPSIS_CONCURRENCY)

        async def translate(anime: Anime, lang: str) -> None:
            async with sem, AsyncSessionLocal() as own:
                try:
                    await synopsis.localized(own, anime, lang)
                except Exception:
                    log.warning("Synopsis (%s) of anime %s failed", lang, anime.id, exc_info=True)

        await asyncio.gather(*(translate(a, lang) for a in animes for lang in _languages()))
        await db.execute(
            update(Anime)
            .where(Anime.id.in_([a.id for a in animes]))
            .values(enriched_at=datetime.now(UTC))
        )
        await db.commit()
        log.info("Catalogue: completed %d show(s)", len(animes))
