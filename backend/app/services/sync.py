import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Anime, ListEntry, Recommendation, User
from app.services import mal
from app.services.recommender import Candidate, ListItem, rank, seed_shows

MAX_CANDIDATE_LOOKUPS = 40
MAL_CONCURRENCY = 4


async def access_token(db: AsyncSession, user: User) -> str:
    if user.token_expires_at - datetime.now(UTC) < timedelta(minutes=5):
        tokens = await mal.refresh_tokens(user.refresh_token)
        user.access_token = tokens.access_token
        user.refresh_token = tokens.refresh_token
        user.token_expires_at = tokens.expires_at
        await db.commit()
    return user.access_token


async def upsert_anime(db: AsyncSession, nodes: list[dict[str, Any]]) -> None:
    rows = list({row["id"]: row for row in map(mal.anime_from_node, nodes)}.values())
    # Chunked to stay below Postgres' 65535 bind-parameter limit on large lists.
    for start in range(0, len(rows), 500):
        chunk = rows[start : start + 500]
        stmt = insert(Anime).values(chunk)
        update_cols = {c: stmt.excluded[c] for c in chunk[0] if c != "id"}
        update_cols["updated_at"] = datetime.now(UTC)
        await db.execute(stmt.on_conflict_do_update(index_elements=[Anime.id], set_=update_cols))


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


async def _gather_limited(coros):
    sem = asyncio.Semaphore(MAL_CONCURRENCY)

    async def run(coro):
        async with sem:
            try:
                return await coro
            except mal.MalError:
                return None

    return await asyncio.gather(*(run(c) for c in coros))


async def sync_user(db: AsyncSession, user: User) -> dict[str, int]:
    """Pull the user's MAL list into the database and recompute their recommendations."""
    async with mal.MalClient(await access_token(db, user)) as client:
        entries = await client.my_animelist()
        await upsert_anime(db, [e["node"] for e in entries])

        await db.execute(delete(ListEntry).where(ListEntry.user_id == user.id))
        items: list[ListItem] = []
        for e in entries:
            node, status = e["node"], e["list_status"]
            db.add(
                ListEntry(
                    user_id=user.id,
                    anime_id=node["id"],
                    status=status["status"],
                    score=status.get("score", 0),
                    episodes_watched=status.get("num_episodes_watched", 0),
                    updated_at=_parse_time(status.get("updated_at")),
                )
            )
            items.append(
                ListItem(
                    anime_id=node["id"],
                    title=node["title"],
                    genres=[g["name"] for g in node.get("genres") or []],
                    status=status["status"],
                    score=status.get("score", 0),
                )
            )

        candidates = await _collect_candidates(db, client, items)

    ranked = rank(items, candidates)
    await db.execute(delete(Recommendation).where(Recommendation.user_id == user.id))
    db.add_all(
        Recommendation(user_id=user.id, anime_id=r.anime_id, score=r.score, reason=r.reason)
        for r in ranked
    )
    user.last_synced_at = datetime.now(UTC)
    await db.commit()
    return {"entries": len(items), "recommendations": len(ranked)}


async def _collect_candidates(
    db: AsyncSession, client: mal.MalClient, items: list[ListItem]
) -> list[Candidate]:
    seeds = seed_shows(items)
    details = await _gather_limited(client.anime(s.anime_id, "recommendations") for s in seeds)

    on_list = {i.anime_id for i in items}
    candidates: dict[int, Candidate] = {}
    for seed, detail in zip(seeds, details, strict=True):
        for rec in (detail or {}).get("recommendations", []):
            anime_id = rec["node"]["id"]
            if anime_id in on_list:
                continue
            c = candidates.setdefault(anime_id, Candidate(anime_id=anime_id))
            c.votes += rec.get("num_recommendations", 0)
            c.seeds.append(seed.anime_id)

    top = sorted(candidates.values(), key=lambda c: c.votes, reverse=True)[:MAX_CANDIDATE_LOOKUPS]
    ids = [c.anime_id for c in top]
    cached = {a.id for a in (await db.scalars(select(Anime).where(Anime.id.in_(ids)))).all()}
    fetched = await _gather_limited(client.anime(i) for i in ids if i not in cached)
    await upsert_anime(db, [node for node in fetched if node])

    known = {a.id: a for a in (await db.scalars(select(Anime).where(Anime.id.in_(ids)))).all()}
    result = []
    for c in top:
        anime = known.get(c.anime_id)
        if anime is None:
            continue
        c.genres, c.mean = anime.genres, anime.mean
        result.append(c)
    return result
