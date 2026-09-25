from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from app.api.deps import DB, OptionalUser
from app.core.cache import get_json, redis, set_json
from app.models import Anime, ListEntry
from app.schemas import GenreOut, SearchResponse
from app.services import catalog, catalog_jobs, jikan, mal
from app.services.tags import KNOWN_TAGS, category
from app.services.taste import predictor_for

router = APIRouter(tags=["search"])

PAGE_SIZE = 24
MAL_MIN_QUERY = 3  # MAL's search rejects shorter queries
GENRES_TTL_SECONDS = 24 * 3600
GENRE_PAGE_TTL_SECONDS = 3600
MAL_SEARCH_TTL_SECONDS = 7 * 24 * 3600
MAL_FAILURE_TTL_SECONDS = 60
CATALOGUE_EXTRA = 12  # catalogue-only matches added to the first page of MAL's results
CATEGORY_ORDER = {"genre": 0, "theme": 1, "demographic": 2, "explicit": 3}


async def _cards(db: DB, user, animes: list[Anime]):
    predictor = await predictor_for(db, user)
    entries: dict[int, ListEntry] = {}
    ids = [a.id for a in animes]
    if user is not None and ids:
        entries = {
            e.anime_id: e
            for e in await db.scalars(
                select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id.in_(ids))
            )
        }
    return [catalog.to_card(a, entries.get(a.id), predictor=predictor) for a in animes]


async def _from_catalogue(db: DB, ids: list[int], rows: dict[int, dict]) -> list[Anime]:
    """The shows in order: from the catalogue when it has them (its data wins), else from the
    fetched `rows`, which are handed to the catalogue worker to be stored in the background."""
    known = {a.id: a for a in await catalog.anime_by_ids(db, ids)}
    missing = [i for i in ids if i not in known and i in rows]
    await catalog_jobs.enqueue(missing, [rows[i] for i in missing])
    await catalog_jobs.complete(list(known.values()))
    return [known[i] if i in known else Anime(**rows[i]) for i in ids if i in known or i in rows]


def _title_matches(q: str):
    pattern = f"%{q}%"
    # Each alternative title on its own: the JSON's text escapes non-ASCII characters.
    alt = func.json_array_elements_text(Anime.alt_titles).table_valued("value").alias("alt")
    return or_(
        Anime.title.ilike(pattern),
        Anime.title_en.ilike(pattern),
        exists(select(1).select_from(alt).where(alt.c.value.ilike(pattern))),
    )


async def _catalogue_search(db: DB, q: str, offset: int, limit: int) -> list[int]:
    return list(
        await db.scalars(
            select(Anime.id)
            .where(_title_matches(q))
            .order_by(Anime.popularity.asc().nulls_last(), Anime.id)
            .offset(offset)
            .limit(limit)
        )
    )


async def _mal_search(q: str, page: int) -> list[dict] | None:
    """MAL's results for a query (one more than a page), cached; None when MAL can't answer."""
    key = f"mal:search:{q.lower()}:{page}"
    nodes = await get_json(key)
    if nodes is None:
        if await redis().exists("mal:search:failed"):
            return None  # MAL failed a moment ago: the catalogue answers meanwhile
        try:
            async with mal.MalClient() as client:
                nodes = await client.search(q, PAGE_SIZE + 1, (page - 1) * PAGE_SIZE)
        except mal.MalError as e:
            if e.outage:
                await redis().set("mal:search:failed", 1, ex=MAL_FAILURE_TTL_SECONDS)
            return None
        await set_json(key, nodes, MAL_SEARCH_TTL_SECONDS)
    return nodes


@router.get("/search", response_model=SearchResponse)
async def search(
    user: OptionalUser,
    db: DB,
    q: str = Query(min_length=1, max_length=100),
    page: int = Query(1, ge=1, le=50),
):
    """Title search over the catalogue (the database, alternative titles included) and MAL.
    MAL's results are cached per query, shows already in the catalogue come from there, and
    new ones are added to it in the background. Without MAL (or for a query too short for
    it) only the catalogue is searched."""
    q = q.strip()
    nodes = None
    if catalog.mal_configured() and len(q) >= MAL_MIN_QUERY:
        nodes = await _mal_search(q, page)
    if nodes is not None:
        ids = [n["id"] for n in nodes[:PAGE_SIZE]]
        if page == 1:
            # Catalogue matches MAL's search doesn't rank (e.g. by a German or other title).
            local = await _catalogue_search(db, q, 0, PAGE_SIZE)
            ids += [i for i in local if i not in ids][:CATALOGUE_EXTRA]
        rows = {n["id"]: mal.anime_from_node(n) for n in nodes}
        return SearchResponse(
            items=await _cards(db, user, await _from_catalogue(db, ids, rows)),
            page=page,
            has_next=len(nodes) > PAGE_SIZE,
            source="mal",
        )

    ids = await _catalogue_search(db, q, (page - 1) * PAGE_SIZE, PAGE_SIZE + 1)
    return SearchResponse(
        items=await _cards(db, user, await _from_catalogue(db, ids[:PAGE_SIZE], {})),
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


@router.get("/search/genre/{genre_id}", response_model=SearchResponse)
async def search_genre(
    genre_id: int,
    user: OptionalUser,
    db: DB,
    page: int = Query(1, ge=1, le=200),
    order: Literal["score", "popularity", "newest"] = "score",
):
    """Shows with a genre/theme/demographic: from Jikan (shows already in the catalogue come
    from there, new ones are added in the background), else from the catalogue."""
    if jikan.enabled():
        key = f"jikan:genre:{genre_id}:{order}:{page}"
        cached = await get_json(key)
        if cached is None:
            try:
                rows, has_next = await jikan.by_genre(genre_id, page, order)
            except jikan.JikanError:
                rows = None
            if rows is not None:
                cached = {"rows": rows, "has_next": has_next}
                await set_json(key, cached, GENRE_PAGE_TTL_SECONDS)
        if cached is not None and "rows" in cached:
            rows = {r["id"]: r for r in cached["rows"]}
            return SearchResponse(
                items=await _cards(db, user, await _from_catalogue(db, list(rows), rows)),
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
        items=await _cards(db, user, await _from_catalogue(db, ids[:PAGE_SIZE], {})),
        page=page,
        has_next=len(ids) > PAGE_SIZE,
        source="local",
    )
