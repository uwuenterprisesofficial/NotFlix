import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Anime, ListEntry, Recommendation, User
from app.services import anilist_account, list_writer, mal, taste
from app.services.recommender import Candidate, ListItem, rank, seed_shows
from app.services.sync_tokens import mal_token

MAX_CANDIDATE_LOOKUPS = 40
MAL_CONCURRENCY = 4


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


@dataclass
class _Entry:
    """One show on the merged list."""

    anime_id: int
    status: str
    score: int
    episodes_watched: int
    updated_at: datetime | None


async def insert_missing_anime(db: AsyncSession, rows: list[dict[str, Any]]) -> None:
    """Add shows that aren't in the catalog yet; ones that are keep their (MAL) data."""
    rows = list({row["id"]: row for row in rows}.values())
    for start in range(0, len(rows), 500):
        stmt = insert(Anime).values(rows[start : start + 500])
        await db.execute(stmt.on_conflict_do_nothing(index_elements=[Anime.id]))


def _anime_client(token: str | None) -> mal.MalClient | None:
    """MAL, as the user when their MAL account is linked, else with the app's client id."""
    if token:
        return mal.MalClient(token)
    return mal.MalClient() if catalog_configured() else None


def catalog_configured() -> bool:
    return bool(get_settings().mal_client_id)


async def sync_user(db: AsyncSession, user: User) -> dict[str, int]:
    """Pull the user's lists (MAL, AniList or both) into the database and recompute their
    recommendations. With both, each list is completed with what only the other has (in the
    background); where both have a show, MAL's entry counts. Show data comes from MAL."""
    token = await mal_token(db, user) if user.has_mal else None
    mal_entries: dict[int, _Entry] = {}
    al_entries: dict[int, anilist_account.AniListEntry] = {}
    skipped = 0

    if token:
        async with mal.MalClient(token) as client:
            raw = await client.my_animelist()
        await upsert_anime(db, [e["node"] for e in raw])
        for e in raw:
            node, status = e["node"], e["list_status"]
            mal_entries[node["id"]] = _Entry(
                node["id"], status["status"], status.get("score", 0),
                status.get("num_episodes_watched", 0), _parse_time(status.get("updated_at")),
            )  # fmt: skip
    if user.has_anilist:
        async with anilist_account.AniListClient(user.anilist_token) as client:
            raw_al = await client.animelist(user.anilist_user_id)
        parsed, skipped = anilist_account.parse_entries(raw_al)
        al_entries = {e.mal_id: e for e in parsed}
        # Shows only AniList has: its data for now; MAL's details are filled in later.
        await insert_missing_anime(
            db, [anilist_account.anime_row(e.media) for e in parsed if e.mal_id not in mal_entries]
        )

    merged: dict[int, _Entry] = {
        mal_id: _Entry(e.mal_id, e.status, e.score, e.episodes_watched, e.updated_at)
        for mal_id, e in al_entries.items()
    } | mal_entries
    await db.flush()

    to_mal = to_anilist = []
    if token and user.has_anilist:
        to_mal = [
            list_writer.Missing(i, e.status, e.episodes_watched, e.score)
            for i, e in al_entries.items()
            if i not in mal_entries
        ]
        to_anilist = [
            list_writer.Missing(i, e.status, e.episodes_watched, e.score)
            for i, e in mal_entries.items()
            if i not in al_entries
        ]

    titles = {
        a.id: a for a in (await db.scalars(select(Anime).where(Anime.id.in_(list(merged))))).all()
    }
    await db.execute(delete(ListEntry).where(ListEntry.user_id == user.id))
    items: list[ListItem] = []
    for e in merged.values():
        anime = titles.get(e.anime_id)
        if anime is None:
            continue
        db.add(
            ListEntry(
                user_id=user.id, anime_id=e.anime_id, status=e.status, score=e.score,
                episodes_watched=e.episodes_watched, updated_at=e.updated_at,
            )
        )  # fmt: skip
        items.append(ListItem(e.anime_id, anime.title, anime.genres or [], e.status, e.score))

    await db.flush()
    user.last_synced_at = datetime.now(UTC)
    predictor = await taste.refit(db, user)
    candidates: list[Candidate] = []
    client = _anime_client(token)
    if client is not None:
        async with client:
            candidates = await _collect_candidates(db, client, items, predictor)

    ranked = rank(items, candidates)
    await db.execute(delete(Recommendation).where(Recommendation.user_id == user.id))
    db.add_all(
        Recommendation(user_id=user.id, anime_id=r.anime_id, score=r.score, reason=r.reason)
        for r in ranked
    )
    await db.commit()
    list_writer.start(user.id, to_mal, to_anilist)
    return {
        "entries": len(items),
        "recommendations": len(ranked),
        "adding_to_mal": len(to_mal),
        "adding_to_anilist": len(to_anilist),
        "skipped": skipped,
    }


async def _collect_candidates(
    db: AsyncSession,
    client: mal.MalClient,
    items: list[ListItem],
    predictor: taste.Predictor | None = None,
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
        if predictor is not None:
            c.predicted = predictor.score(taste.Show.of(anime))
        result.append(c)
    return result
