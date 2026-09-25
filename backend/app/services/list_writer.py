"""Adds the entries missing on one of a user's lists (MAL or AniList) to it, in the background
(in the API process): AniList allows only a few dozen requests a minute, so a first sync of
two long lists takes a while."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.db.session import AsyncSessionLocal
from app.models import User
from app.services import anilist_account, mal
from app.services.sync_tokens import mal_token

log = logging.getLogger(__name__)

ANILIST_PAUSE_S = 0.8  # between writes, to stay below AniList's rate limit
MAL_CONCURRENCY = 2


@dataclass(frozen=True)
class Missing:
    mal_id: int
    status: str  # MAL list status
    episodes_watched: int
    score: int  # 0 = unscored


_running: dict[int, asyncio.Task] = {}
_progress: dict[int, dict[str, dict[str, int]]] = {}


def progress(user_id: int) -> dict[str, dict[str, int]] | None:
    """{"mal": {"done", "total", "failed"}, "anilist": {...}} while writing, else None."""
    return _progress.get(user_id) if user_id in _running else None


def start(user_id: int, to_mal: list[Missing], to_anilist: list[Missing]) -> None:
    if user_id in _running or not (to_mal or to_anilist):
        return
    _progress[user_id] = {
        "mal": {"done": 0, "total": len(to_mal), "failed": 0},
        "anilist": {"done": 0, "total": len(to_anilist), "failed": 0},
    }
    task = asyncio.create_task(_run(user_id, to_mal, to_anilist))
    _running[user_id] = task
    task.add_done_callback(lambda _: _running.pop(user_id, None))


async def wait_idle() -> None:
    while _running:
        await asyncio.gather(*list(_running.values()), return_exceptions=True)


async def _to_mal(token: str, items: list[Missing], state: dict[str, int]) -> None:
    sem = asyncio.Semaphore(MAL_CONCURRENCY)
    async with mal.MalClient(token) as client:

        async def add(item: Missing) -> None:
            fields: dict[str, Any] = {
                "status": item.status,
                "num_watched_episodes": item.episodes_watched,
            }
            if item.score:
                fields["score"] = item.score
            async with sem:
                try:
                    await client.update_my_list_status(item.mal_id, **fields)
                except mal.MalError as e:
                    log.info("Adding anime %s to MAL failed: %s", item.mal_id, e)
                    state["failed"] += 1
                finally:
                    state["done"] += 1

        await asyncio.gather(*(add(i) for i in items))


async def _to_anilist(token: str, items: list[Missing], state: dict[str, int]) -> None:
    async with anilist_account.AniListClient(token) as client:
        ids = await client.ids_for([i.mal_id for i in items])
        for item in items:
            media_id = ids.get(item.mal_id)
            try:
                if media_id is None:
                    raise anilist_account.AniListError("not on AniList")
                await client.save_entry(media_id, item.status, item.episodes_watched, item.score)
            except anilist_account.AniListError as e:
                log.info("Adding anime %s to AniList failed: %s", item.mal_id, e)
                state["failed"] += 1
            state["done"] += 1
            await asyncio.sleep(ANILIST_PAUSE_S)


async def _run(user_id: int, to_mal: list[Missing], to_anilist: list[Missing]) -> None:
    state = _progress[user_id]
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if user is None:
                return
            jobs = []
            if to_mal and user.has_mal:
                jobs.append(_to_mal(await mal_token(db, user), to_mal, state["mal"]))
            if to_anilist and user.has_anilist:
                jobs.append(_to_anilist(user.anilist_token, to_anilist, state["anilist"]))
            await asyncio.gather(*jobs)
    except Exception:
        log.exception("Writing missing list entries for user %s failed", user_id)
