from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB, insert

from app.api.deps import DB, OptionalUser
from app.core.cache import get_json, set_json
from app.models import Anime, ListEntry
from app.schemas import GenreOut, SearchResponse
from app.services import catalog, jikan, mal
from app.services.sync import upsert_anime
from app.services.tags import KNOWN_TAGS, category
from app.services.taste import predictor_for

router = APIRouter(tags=["search"])

PAGE_SIZE = 24
MAL_MIN_QUERY = 3  # MAL's search rejects shorter queries
GENRES_TTL_SECONDS = 24 * 3600
GENRE_PAGE_TTL_SECONDS = 3600
CATEGORY_ORDER = {"genre": 0, "theme": 1, "demographic": 2, "explicit": 3}


async def _cards(db: DB, user, ids: list[int]):
    predictor = await predictor_for(db, user)
    entries: dict[int, ListEntry] = {}
    if user is not None and ids:
        entries = {
            e.anime_id: e
            for e in await db.scalars(
                select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id.in_(ids))
            )
        }
    return [
        catalog.to_card(a, entries.get(a.id), predictor=predictor)
        for a in await catalog.anime_by_ids(db, ids)
    ]


@router.get("/search", response_model=SearchResponse)
async def search(
    user: OptionalUser,
    db: DB,
    q: str = Query(min_length=1, max_length=100),
    page: int = Query(1, ge=1, le=50),
):
    """Title search: MyAnimeList's own search, or the local catalog when MAL isn't set up (or
    the query is too short for it)."""
    q = q.strip()
    offset = (page - 1) * PAGE_SIZE
    if catalog.mal_configured() and len(q) >= MAL_MIN_QUERY:
        try:
            async with mal.MalClient() as client:
                # One more than a page tells whether there is a next one.
                nodes = await client.search(q, PAGE_SIZE + 1, offset)
        except mal.MalError as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
        if nodes:
            await upsert_anime(db, nodes)
            await db.commit()
        ids = [n["id"] for n in nodes[:PAGE_SIZE]]
        return SearchResponse(
            items=await _cards(db, user, ids),
            page=page,
            has_next=len(nodes) > PAGE_SIZE,
            source="mal",
        )

    pattern = f"%{q}%"
    ids = list(
        await db.scalars(
            select(Anime.id)
            .where(or_(Anime.title.ilike(pattern), Anime.title_en.ilike(pattern)))
            .order_by(Anime.popularity.asc().nulls_last(), Anime.id)
            .offset(offset)
            .limit(PAGE_SIZE + 1)
        )
    )
    return SearchResponse(
        items=await _cards(db, user, ids[:PAGE_SIZE]),
        page=page,
        has_next=len(ids) > PAGE_SIZE,
        source="local",
    )


@router.get("/genres", response_model=list[GenreOut])
async def genres():
    """Every genre, theme and demographic to pick from, grouped as MAL's site does."""
    found = await get_json("jikan:genres") if jikan.enabled() else None
    if found is None and jikan.enabled():
        try:
            found = await jikan.genres()
            await set_json("jikan:genres", found, GENRES_TTL_SECONDS)
        except jikan.JikanError:
            found = None
    if not found:
        found = [{"id": i, "name": name, "count": None} for i, name in KNOWN_TAGS.items()]
    unique = {g["id"]: g for g in found}.values()
    out = [GenreOut(category=category(g["id"]), **g) for g in unique]
    out.sort(key=lambda g: (CATEGORY_ORDER[g.category], g.name.lower()))
    return out


async def _upsert_missing(db: DB, rows: list[dict]) -> None:
    """Add Jikan's shows to the catalog. A show already there keeps MAL's own data, unless it
    lacks the genre ids (cached before they were stored)."""
    for row in {r["id"]: r for r in rows}.values():
        stmt = insert(Anime).values(row)
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=[Anime.id],
                set_={c: stmt.excluded[c] for c in row if c != "id"},
                where=func.json_array_length(Anime.genre_tags) == 0,
            )
        )


@router.get("/search/genre/{genre_id}", response_model=SearchResponse)
async def search_genre(
    genre_id: int,
    user: OptionalUser,
    db: DB,
    page: int = Query(1, ge=1, le=200),
    order: Literal["score", "popularity", "newest"] = "score",
):
    """Shows with a genre/theme/demographic: from Jikan, else from the local catalog."""
    if jikan.enabled():
        key = f"jikan:genre:{genre_id}:{order}:{page}"
        cached = await get_json(key)
        if cached is None:
            try:
                rows, has_next = await jikan.by_genre(genre_id, page, order)
            except jikan.JikanError:
                rows = None
            if rows is not None:
                await _upsert_missing(db, rows)
                await db.commit()
                cached = {"ids": [r["id"] for r in rows], "has_next": has_next}
                await set_json(key, cached, GENRE_PAGE_TTL_SECONDS)
        if cached is not None:
            return SearchResponse(
                items=await _cards(db, user, cached["ids"]),
                page=page,
                has_next=cached["has_next"],
                source="jikan",
            )

    sort = {
        "score": Anime.mean.desc().nulls_last(),
        "popularity": Anime.num_list_users.desc().nulls_last(),
        "newest": Anime.start_year.desc().nulls_last(),
    }[order]
    ids = list(
        await db.scalars(
            select(Anime.id)
            .where(cast(Anime.genre_tags, JSONB).contains([{"id": genre_id}]))
            .order_by(sort, Anime.id)
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE + 1)
        )
    )
    return SearchResponse(
        items=await _cards(db, user, ids[:PAGE_SIZE]),
        page=page,
        has_next=len(ids) > PAGE_SIZE,
        source="local",
    )
