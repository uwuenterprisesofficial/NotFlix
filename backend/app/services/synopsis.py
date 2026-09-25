"""Synopses in the UI's language. MAL's are English; German ones come from AniWorld (the
series page of the show's AniWorld mapping). Found (or not found) texts are stored, so each
show is looked up once; a miss is retried after a week."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Anime, AnimeSynopsis
from app.providers import base as providers_base
from app.providers.base import AnimeInfo

log = logging.getLogger(__name__)

# Which provider has synopses in which language.
SOURCES = {"de": "aniworld"}
RETRY_MISSING_AFTER = timedelta(days=7)
LOOKUP_TIMEOUT_S = 45

_lookups: dict[tuple[int, str], asyncio.Task] = {}


def supported(language: str) -> bool:
    return language in SOURCES


async def stored(db: AsyncSession, anime_id: int, language: str) -> AnimeSynopsis | None:
    return await db.scalar(
        select(AnimeSynopsis).where(
            AnimeSynopsis.anime_id == anime_id, AnimeSynopsis.language == language
        )
    )


async def _lookup(anime: AnimeInfo, language: str) -> tuple[str | None, str | None]:
    name = SOURCES[language]
    provider = next((p for p in providers_base.enabled_providers() if p.name == name), None)
    if provider is None or not hasattr(provider, "description"):
        return None, None
    try:
        text = await asyncio.wait_for(provider.description(anime), LOOKUP_TIMEOUT_S)
    except Exception as e:  # provider down, timeout, ...: counts as not found for now
        log.info("No %s synopsis for anime %s: %s", language, anime.id, e)
        return None, name
    return text, name


async def localized(db: AsyncSession, anime: Anime, language: str) -> str | None:
    """The synopsis in `language`: stored, else looked up now (concurrent callers share one
    lookup). None when there is none."""
    if not supported(language):
        return None
    row = await stored(db, anime.id, language)
    if row is not None and (
        row.synopsis or datetime.now(UTC) - row.fetched_at < RETRY_MISSING_AFTER
    ):
        return row.synopsis
    key = (anime.id, language)
    task = _lookups.get(key)
    if task is None:
        task = asyncio.create_task(_lookup(AnimeInfo.from_model(anime), language))
        _lookups[key] = task
        task.add_done_callback(lambda _: _lookups.pop(key, None))
    text, source = await asyncio.shield(task)
    stmt = insert(AnimeSynopsis).values(
        anime_id=anime.id, language=language, synopsis=text, source=source,
        fetched_at=datetime.now(UTC),
    )  # fmt: skip
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[AnimeSynopsis.anime_id, AnimeSynopsis.language],
            set_={
                "synopsis": stmt.excluded.synopsis,
                "source": stmt.excluded.source,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )  # fmt: skip
    )
    await db.commit()
    return text
