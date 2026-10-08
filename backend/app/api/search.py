import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from app.api.deps import DB, OptionalUser
from app.core.cache import get_json, redis, set_json
from app.db.session import AsyncSessionLocal
from app.models import Anime, EpisodeSource, ListEntry, ListStatus
from app.schemas import GenreOut, SearchResponse
from app.services import catalog, catalog_jobs, caught_up, jikan, mal
from app.services.sync import insert_missing_anime
from app.services.tags import KNOWN_TAGS, category
from app.services.taste import Show, predictor_for

log = logging.getLogger(__name__)
router = APIRouter(tags=["search"])

PAGE_SIZE = 24
MAL_MIN_QUERY = 3  # MAL's search rejects shorter queries
GENRES_TTL_SECONDS = 24 * 3600
GENRE_PAGE_TTL_SECONDS = 3600
MAL_SEARCH_TTL_SECONDS = 7 * 24 * 3600
MAL_FAILURE_TTL_SECONDS = 60
CATALOGUE_EXTRA = 12  # catalogue-only matches added to the first page of MAL's results
CATEGORY_ORDER = {"genre": 0, "theme": 1, "demographic": 2, "explicit": 3}


DUBS = ("de-dub", "en-dub")


async def _dubs(db: DB, ids: list[int]) -> dict[int, list[str]]:
    """The dubs NotFlix has found streams of, per show (shows whose streams were looked up)."""
    found: dict[int, list[str]] = {}
    if ids:
        rows = await db.execute(
            select(EpisodeSource.anime_id, EpisodeSource.language)
            .where(EpisodeSource.anime_id.in_(ids), EpisodeSource.language.in_(DUBS))
            .distinct()
        )
        for anime_id, language in rows:
            found.setdefault(anime_id, []).append(language)
    return {anime_id: sorted(langs) for anime_id, langs in found.items()}


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
    dubs = await _dubs(db, ids)
    cards = [catalog.to_card(a, entries.get(a.id), predictor=predictor) for a in animes]
    for card in cards:
        card.dubs = dubs.get(card.id, [])
    await caught_up.mark(db, cards)
    return cards


Order = Literal["score", "popularity", "newest", "for_you"]
SORTS = {
    "score": Anime.mean.desc().nulls_last(),
    "popularity": Anime.num_list_users.desc().nulls_last(),
    "newest": Anime.start_year.desc().nulls_last(),
}
# Seen: on the list as anything but plan to watch.
SEEN = (ListStatus.watching, ListStatus.completed, ListStatus.on_hold, ListStatus.dropped)
PREDICT_POOL = 3000  # shows predicted at most for "for you" or a predicted-score range


@dataclass
class Filters:
    hide_seen: bool = False
    min_score: float | None = None  # MAL's score
    max_score: float | None = None
    min_predicted: float | None = None  # the user's predicted score
    max_predicted: float | None = None

    @property
    def by_prediction(self) -> bool:
        return self.min_predicted is not None or self.max_predicted is not None


def filters(
    hide_seen: bool = False,
    min_score: float | None = Query(None, ge=0, le=10),
    max_score: float | None = Query(None, ge=0, le=10),
    min_predicted: float | None = Query(None, ge=0, le=10),
    max_predicted: float | None = Query(None, ge=0, le=10),
) -> Filters:
    return Filters(hide_seen, min_score, max_score, min_predicted, max_predicted)


SearchFilters = Annotated[Filters, Depends(filters)]


def _sort_key(order: str):
    if order == "popularity":
        return lambda a: -(a.num_list_users or 0)
    if order == "newest":
        return lambda a: -(a.start_year or 0)
    return lambda a: -(a.mean or 0)


async def _catalogue_page(db: DB, user, where, order: str, page: int, f: Filters):
    """One page of catalogue shows matching `where` and the filters: (cards, has_next). Ordered
    by "for you" or filtered by predicted score, the most popular PREDICT_POOL shows are
    predicted and sorted here; otherwise the database does it all."""
    query = select(Anime).where(where)
    if f.min_score is not None:
        query = query.where(Anime.mean >= f.min_score)
    if f.max_score is not None:
        query = query.where(Anime.mean <= f.max_score)
    if f.hide_seen and user is not None:
        seen = select(ListEntry.anime_id).where(
            ListEntry.user_id == user.id, ListEntry.status.in_(SEEN)
        )
        query = query.where(Anime.id.not_in(seen))
    predictor = await predictor_for(db, user)
    start = (page - 1) * PAGE_SIZE
    if predictor is None or not (order == "for_you" or f.by_prediction):
        sort = SORTS["score" if order == "for_you" else order]
        found = list(
            await db.scalars(query.order_by(sort, Anime.id).offset(start).limit(PAGE_SIZE + 1))
        )
        return await _cards(db, user, found[:PAGE_SIZE]), len(found) > PAGE_SIZE

    pool = list(
        await db.scalars(
            query.order_by(Anime.num_list_users.desc().nulls_last(), Anime.id).limit(PREDICT_POOL)
        )
    )
    scored = {}
    if user is not None and pool:
        scored = {
            e.anime_id: e.score
            for e in await db.scalars(
                select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.score > 0)
            )
        }
    predicted = {
        a.id: float(scored[a.id]) if a.id in scored else predictor.predict(Show.of(a)).score
        for a in pool
    }
    lo = f.min_predicted if f.min_predicted is not None else 0
    hi = f.max_predicted if f.max_predicted is not None else 10
    pool = [a for a in pool if lo <= predicted[a.id] <= hi]
    pool.sort(key=(lambda a: -predicted[a.id]) if order == "for_you" else _sort_key(order))
    return await _cards(db, user, pool[start : start + PAGE_SIZE]), len(pool) > start + PAGE_SIZE


def _keep(card, f: Filters) -> bool:
    """Whether a card passes the filters (for results that don't come from the catalogue)."""
    if f.hide_seen and card.progress is not None and card.progress.status in SEEN:
        return False
    if f.min_score is not None and (card.mean is None or card.mean < f.min_score):
        return False
    if f.max_score is not None and (card.mean is None or card.mean > f.max_score):
        return False
    if f.by_prediction:
        own = card.progress.score if card.progress and card.progress.score else None
        value = own if own is not None else (card.prediction.score if card.prediction else None)
        lo = f.min_predicted if f.min_predicted is not None else 0
        hi = f.max_predicted if f.max_predicted is not None else 10
        if value is None or not lo <= value <= hi:
            return False
    return True


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
    f: SearchFilters,
    q: str = Query(min_length=1, max_length=100),
    page: int = Query(1, ge=1, le=50),
    quick: bool = False,
):
    """Title search over the catalogue (the database, alternative titles included) and MAL.
    MAL's results are cached per query, shows already in the catalogue come from there, and
    new ones are added to it in the background. Without MAL (or for a query too short for
    it) only the catalogue is searched. `quick` searches only the catalogue (milliseconds):
    the search page shows that while MAL's answer is on its way."""
    q = q.strip()
    nodes = None
    if not quick and catalog.mal_configured() and len(q) >= MAL_MIN_QUERY:
        nodes = await _mal_search(q, page)
    if nodes is not None:
        ids = [n["id"] for n in nodes[:PAGE_SIZE]]
        if page == 1:
            # Catalogue matches MAL's search doesn't rank (e.g. by a German or other title).
            local = await _catalogue_search(db, q, 0, PAGE_SIZE)
            ids += [i for i in local if i not in ids][:CATALOGUE_EXTRA]
        rows = {n["id"]: mal.anime_from_node(n) for n in nodes}
        cards = await _cards(db, user, await _from_catalogue(db, ids, rows))
        return SearchResponse(
            items=[c for c in cards if _keep(c, f)],
            page=page,
            has_next=len(nodes) > PAGE_SIZE,
            source="mal",
        )

    ids = await _catalogue_search(db, q, (page - 1) * PAGE_SIZE, PAGE_SIZE + 1)
    cards = await _cards(db, user, await _from_catalogue(db, ids[:PAGE_SIZE], {}))
    return SearchResponse(
        items=[c for c in cards if _keep(c, f)],
        page=page,
        has_next=len(ids) > PAGE_SIZE,
        source="local",
    )


_genres_refresh: asyncio.Task | None = None


async def _refresh_genres() -> None:
    with contextlib.suppress(jikan.JikanError):
        await set_json("jikan:genres", await jikan.genres(), GENRES_TTL_SECONDS)


@router.get("/search/dubbed", response_model=SearchResponse)
async def search_dubbed(
    user: OptionalUser,
    db: DB,
    f: SearchFilters,
    language: Literal["de-dub", "en-dub"] = "de-dub",
    page: int = Query(1, ge=1, le=200),
    order: Order = "popularity",
):
    """Shows NotFlix has found dubbed streams of (in one language), from the shared stream
    cache: every show someone opened adds to it."""
    dubbed = select(EpisodeSource.anime_id).where(EpisodeSource.language == language)
    cards, has_next = await _catalogue_page(db, user, Anime.id.in_(dubbed), order, page, f)
    return SearchResponse(items=cards, page=page, has_next=has_next, source="local")


@router.get("/genres", response_model=list[GenreOut])
async def genres():
    """Every genre, theme and demographic to pick from, grouped as MAL's site does. Never waits
    for Jikan: until its list (with counts) is cached, the known tags answer and it's fetched
    in the background (the search page shouldn't wait for it)."""
    global _genres_refresh
    found = await get_json("jikan:genres") if jikan.enabled() else None
    if found is None and jikan.enabled() and (_genres_refresh is None or _genres_refresh.done()):
        _genres_refresh = asyncio.create_task(_refresh_genres())
    if not found:
        found = [{"id": i, "name": name, "count": None} for i, name in KNOWN_TAGS.items()]
    unique = {g["id"]: g for g in found}.values()
    out = [GenreOut(category=category(g["id"]), **g) for g in unique]
    out.sort(key=lambda g: (CATEGORY_ORDER[g.category], g.name.lower()))
    return out


GENRE_IMPORT_AHEAD = 1  # Jikan pages fetched past the one asked for
_imports: dict[tuple[int, str], asyncio.Task] = {}


async def _import_genre(genre_id: int, order: str, last_page: int) -> None:
    """Add Jikan's shows with the genre (its first pages in this order) to the catalogue."""
    for page in range(1, last_page + 1):
        key = f"jikan:genre:{genre_id}:{order}:{page}"
        if (done := await get_json(key)) is not None:
            if not done.get("has_next"):
                return
            continue
        try:
            rows, has_next = await jikan.by_genre(genre_id, page, order)  # type: ignore[arg-type]
        except jikan.JikanError as e:
            log.info("Jikan genre %s page %s: %s", genre_id, page, e)
            return
        async with AsyncSessionLocal() as db:
            await insert_missing_anime(db, rows)
            await db.commit()
            await catalog_jobs.complete(await catalog.anime_by_ids(db, [r["id"] for r in rows]))
        await set_json(key, {"has_next": has_next}, GENRE_PAGE_TTL_SECONDS)
        if not has_next:
            return


async def _importing(genre_id: int, order: str, page: int) -> bool:
    """Start adding the genre's shows from Jikan in the background (when not done lately);
    whether that's still going on."""
    if not jikan.enabled():
        return False
    task = _imports.get((genre_id, order))
    if task is None or task.done():
        last = page + GENRE_IMPORT_AHEAD
        done = await get_json(f"jikan:genre:{genre_id}:{order}:{last}")
        if done is not None:
            return False
        task = asyncio.create_task(_import_genre(genre_id, order, last))
        _imports[(genre_id, order)] = task
        task.add_done_callback(lambda _: _imports.pop((genre_id, order), None))
    return not task.done()


async def wait_imports() -> None:
    """Wait for genre imports (tests)."""
    while _imports:
        await asyncio.gather(*list(_imports.values()), return_exceptions=True)


@router.get("/search/genre/{genre_id}", response_model=SearchResponse)
async def search_genre(
    genre_id: int,
    user: OptionalUser,
    db: DB,
    f: SearchFilters,
    page: int = Query(1, ge=1, le=200),
    order: Order = "score",
):
    """Shows with a genre/theme/demographic, from the catalogue: answered at once. Jikan's
    shows with the genre are added to the catalogue in the background meanwhile (`pending`:
    ask again in a moment for more)."""
    jikan_order = "score" if order == "for_you" else order
    pending = await _importing(genre_id, jikan_order, page)
    tagged = cast(Anime.genre_tags, JSONB).contains([{"id": genre_id}])
    cards, has_next = await _catalogue_page(db, user, tagged, order, page, f)
    return SearchResponse(
        items=cards, page=page, has_next=has_next or pending, source="local", pending=pending
    )
