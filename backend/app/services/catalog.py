from datetime import UTC, datetime, timedelta
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_json, set_json
from app.core.config import get_settings
from app.models import Anime, ListEntry
from app.schemas import AnimeCard, AnimeDetail, PredictionOut, Progress, ReasonOut, TagOut
from app.services import mal
from app.services.sync import upsert_anime
from app.services.tags import category, tags_from_names
from app.services.taste import Predictor, Show

RANKING_TTL_SECONDS = 3600
ANIME_STALE_AFTER = timedelta(days=7)


def mal_configured() -> bool:
    return bool(get_settings().mal_client_id)


CardT = TypeVar("CardT", AnimeCard, AnimeDetail)


def predicts(entry: ListEntry | None) -> bool:
    """Whether a show gets a predicted score: not when the user scored or dropped it."""
    return entry is None or (entry.score == 0 and entry.status != "dropped")


def _build(
    model: type[CardT],
    anime: Anime,
    entry: ListEntry | None,
    reason: str | None,
    predictor: Predictor | None,
    reasons: int = 0,
) -> CardT:
    card = model.model_validate(anime)
    if entry is not None:
        card.progress = Progress(
            status=entry.status, episodes_watched=entry.episodes_watched, score=entry.score
        )
    card.reason = reason
    if predictor is not None and predicts(entry):
        p = predictor.predict(Show.of(anime), reasons)
        card.prediction = PredictionOut(
            score=p.score,
            tier=p.tier,
            reasons=[ReasonOut(key=k, name=n, points=v) for k, n, v in p.reasons],
        )
    return card


def to_card(
    anime: Anime,
    entry: ListEntry | None = None,
    reason: str | None = None,
    predictor: Predictor | None = None,
) -> AnimeCard:
    return _build(AnimeCard, anime, entry, reason, predictor)


def to_detail(
    anime: Anime,
    entry: ListEntry | None = None,
    reason: str | None = None,
    predictor: Predictor | None = None,
) -> AnimeDetail:
    detail = _build(AnimeDetail, anime, entry, reason, predictor, reasons=6)
    detail.tags = [
        TagOut(id=t["id"], name=t["name"], category=category(t["id"]))
        for t in anime.genre_tags or tags_from_names(anime.genres or [])
    ]
    return detail


async def anime_by_ids(db: AsyncSession, ids: list[int]) -> list[Anime]:
    found = {a.id: a for a in (await db.scalars(select(Anime).where(Anime.id.in_(ids)))).all()}
    return [found[i] for i in ids if i in found]


async def ranking(db: AsyncSession, ranking_type: str, limit: int = 20) -> list[Anime]:
    """MAL ranking lists (airing, bypopularity, upcoming, ...), cached in Redis for an hour."""
    key = f"mal:ranking:{ranking_type}:{limit}"
    cached = await get_json(key)
    if cached is not None:
        return await anime_by_ids(db, cached)

    async with mal.MalClient() as client:
        nodes = await client.ranking(ranking_type, limit)
    await upsert_anime(db, nodes)
    await db.commit()
    ids = [n["id"] for n in nodes]
    await set_json(key, ids, RANKING_TTL_SECONDS)
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
