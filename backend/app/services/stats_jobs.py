"""Statistics are computed in the background (in the API process) and cached in Redis, so the
statistics page never waits on MyAnimeList.

A run first fills in the details the statistics and predictions need (genre ids, studios,
source, members, ...) for listed shows that lack them, e.g. shows cached before those were
stored: MAL's list endpoint is tried first (one request per 1000 shows), then each show that is
still missing something is fetched on its own. Then the user's model is refitted and the
statistics are computed and cached until the next list sync.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select

from app.core.cache import get_json, redis, set_json
from app.db.session import AsyncSessionLocal
from app.models import Anime, ListEntry, User
from app.services import catalog, mal, stats, taste
from app.services.sync import MAL_CONCURRENCY, upsert_anime
from app.services.sync_tokens import mal_token

log = logging.getLogger(__name__)

CACHE_TTL_S = 30 * 24 * 3600
# A show whose details couldn't be fetched isn't tried again for this long.
RETRY_DETAILS_AFTER_S = 24 * 3600
MAX_DETAIL_FETCHES = 2000

_running: dict[int, asyncio.Task] = {}
_progress: dict[int, dict[str, Any]] = {}


def _key(user_id: int) -> str:
    return f"stats:{user_id}"


STATS_FORMAT = 2  # bump when the shape of the statistics changes


def _version(user: User) -> str:
    """Cached statistics belong to one state of the list (its last sync) and one format."""
    synced = user.last_synced_at.isoformat() if user.last_synced_at else "never"
    return f"{STATS_FORMAT}:{synced}"


async def cached(user_id: int) -> dict[str, Any] | None:
    return await get_json(_key(user_id))


async def forget(user_id: int) -> None:
    await redis().delete(_key(user_id))


def progress(user_id: int) -> dict[str, Any] | None:
    return _progress.get(user_id)


def clear_failure(user_id: int) -> None:
    """Let the next status() try again after a failed computation."""
    if _progress.get(user_id, {}).get("status") == "failed":
        _progress.pop(user_id, None)


def running(user_id: int) -> bool:
    return user_id in _running


async def status(user: User) -> dict[str, Any]:
    """What the statistics page shows: the cached statistics (if any) and whether newer ones
    are being computed. Starts that computation when the cache is missing or out of date."""
    entry = await cached(user.id)
    if entry is not None and not str(entry.get("version", "")).startswith(f"{STATS_FORMAT}:"):
        entry = None  # an older format can't even be shown while newer ones are computed
    fresh = entry is not None and entry["version"] == _version(user)
    state = _progress.get(user.id, {})
    if not fresh and not running(user.id) and state.get("status") != "failed":
        start(user.id)
        state = _progress[user.id]
    if fresh and not running(user.id):
        return {"status": "ready", "stats": entry["stats"], "computed_at": entry["computed_at"]}
    return {
        "status": "failed" if state.get("status") == "failed" else "loading",
        "step": state.get("step"),
        "done": state.get("done", 0),
        "total": state.get("total", 0),
        "error": state.get("error"),
        "stats": entry["stats"] if entry else None,
        "computed_at": entry["computed_at"] if entry else None,
    }


def start(user_id: int) -> None:
    """Compute a user's statistics in the background, unless that's already happening."""
    if user_id in _running:
        return
    _progress[user_id] = {"status": "running", "step": "starting", "done": 0, "total": 0}
    task = asyncio.create_task(_run(user_id))
    _running[user_id] = task
    task.add_done_callback(lambda _: _running.pop(user_id, None))


async def wait_idle() -> None:
    """Wait for running computations (tests, shutdown)."""
    while _running:
        await asyncio.gather(*list(_running.values()), return_exceptions=True)


def _needs_details():
    """Listed shows without the details statistics use (never fetched since they were added)."""
    return or_(
        func.json_array_length(Anime.genre_tags) == 0,
        Anime.num_list_users.is_(None),
    )


async def _missing(db, user_id: int) -> list[int]:
    ids = list(
        await db.scalars(
            select(Anime.id)
            .join(ListEntry, ListEntry.anime_id == Anime.id)
            .where(ListEntry.user_id == user_id, _needs_details())
        )
    )
    if not ids:
        return []
    tried = await redis().mget([f"anime:details-tried:{i}" for i in ids])
    return [i for i, t in zip(ids, tried, strict=True) if t is None]


async def _fill_details(db, user: User) -> None:
    state = _progress[user.id]
    missing = await _missing(db, user.id)
    if not missing or not catalog.mal_configured():
        return
    state.update(step="details", done=0, total=len(missing))
    # As the user when their MAL account is linked, else with the app's client id.
    token = await mal_token(db, user) if user.has_mal else None
    async with mal.MalClient(token) as client:
        # The list endpoint returns most details for every show in a request or two.
        try:
            if token:
                entries = await client.my_animelist()
                await upsert_anime(db, [e["node"] for e in entries])
                await db.commit()
        except mal.MalError as e:
            log.warning("Refreshing the list of user %s failed: %s", user.id, e)
        missing = (await _missing(db, user.id))[:MAX_DETAIL_FETCHES]
        state.update(done=0, total=len(missing))

        sem = asyncio.Semaphore(MAL_CONCURRENCY)

        async def fetch(anime_id: int) -> dict[str, Any] | None:
            async with sem:
                try:
                    return await client.anime(anime_id)
                except mal.MalError as e:
                    log.info("Details of anime %s: %s", anime_id, e)
                    return None
                finally:
                    state["done"] += 1

        nodes = await asyncio.gather(*(fetch(i) for i in missing))
    found = [n for n in nodes if n]
    if found:
        await upsert_anime(db, found)
        await db.commit()
    # Whatever is still incomplete (e.g. MAL has no studio for it) isn't asked for every time.
    if missing:
        pipe = redis().pipeline()
        for anime_id in missing:
            pipe.set(f"anime:details-tried:{anime_id}", 1, ex=RETRY_DETAILS_AFTER_S)
        await pipe.execute()


async def _run(user_id: int) -> None:
    state = _progress[user_id]
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if user is None:
                return
            version = _version(user)
            try:
                await _fill_details(db, user)
            except Exception as e:  # MAL down etc.: compute with what there is
                log.warning("Filling in show details for user %s failed: %s", user_id, e)
                await db.rollback()
            state.update(step="computing", done=0, total=0)
            rated = await taste.load_rated(db, user_id)
            predictor = await taste.refit(db, user, rated)
            await db.commit()
            # CPU-bound: keep the event loop free for other requests.
            result = await asyncio.to_thread(stats.compute, rated, predictor)
            await set_json(
                _key(user_id),
                {
                    "version": version,
                    "computed_at": datetime.now(UTC).isoformat(),
                    "stats": result,
                },
                CACHE_TTL_S,
            )
        _progress.pop(user_id, None)
    except Exception as e:
        log.exception("Statistics for user %s failed", user_id)
        state.update(status="failed", error=str(e)[:300])
