import json
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Anime, ListEntry
from app.schemas import AnimeCard, AnimeDetail, Progress
from app.services import mal
from app.services.sync import upsert_anime

RANKING_TTL_SECONDS = 3600
ANIME_STALE_AFTER = timedelta(days=7)

_redis: Redis | None = None


def redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url)
    return _redis


def mal_configured() -> bool:
    return bool(get_settings().mal_client_id)


CardT = TypeVar("CardT", AnimeCard, AnimeDetail)


def _build(model: type[CardT], anime: Anime, entry: ListEntry | None, reason: str | None) -> CardT:
    card = model.model_validate(anime)
    if entry is not None:
        card.progress = Progress(
            status=entry.status, episodes_watched=entry.episodes_watched, score=entry.score
        )
    card.reason = reason
    return card


def to_card(anime: Anime, entry: ListEntry | None = None, reason: str | None = None) -> AnimeCard:
    return _build(AnimeCard, anime, entry, reason)


def to_detail(
    anime: Anime, entry: ListEntry | None = None, reason: str | None = None
) -> AnimeDetail:
    return _build(AnimeDetail, anime, entry, reason)


async def anime_by_ids(db: AsyncSession, ids: list[int]) -> list[Anime]:
    found = {a.id: a for a in (await db.scalars(select(Anime).where(Anime.id.in_(ids)))).all()}
    return [found[i] for i in ids if i in found]


async def ranking(db: AsyncSession, ranking_type: str, limit: int = 20) -> list[Anime]:
    """MAL ranking lists (airing, bypopularity, upcoming, ...), cached in Redis for an hour."""
    key = f"mal:ranking:{ranking_type}:{limit}"
    cached = await redis().get(key)
    if cached is not None:
        return await anime_by_ids(db, json.loads(cached))

    async with mal.MalClient() as client:
        nodes = await client.ranking(ranking_type, limit)
    await upsert_anime(db, nodes)
    await db.commit()
    ids = [n["id"] for n in nodes]
    await redis().set(key, json.dumps(ids), ex=RANKING_TTL_SECONDS)
    return await anime_by_ids(db, ids)


async def get_anime(db: AsyncSession, anime_id: int) -> Anime | None:
    anime = await db.get(Anime, anime_id)
    fresh = anime is not None and datetime.now(UTC) - anime.updated_at < ANIME_STALE_AFTER
    if fresh or not mal_configured():
        return anime
    try:
        async with mal.MalClient() as client:
            node = await client.anime(anime_id)
    except mal.MalError:
        return anime
    await upsert_anime(db, [node])
    await db.commit()
    if anime is not None:
        await db.refresh(anime)
        return anime
    return await db.get(Anime, anime_id)
