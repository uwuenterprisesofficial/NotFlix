"""List syncs in the background (in the API process): the first one after signing in, and one
after linking another list, so the list and recommendations appear without pressing "Sync".
POST /me/sync during one waits for it instead of starting another."""

import asyncio
import logging
from typing import Any

from app.db.session import AsyncSessionLocal
from app.models import User
from app.services import stats_jobs

log = logging.getLogger(__name__)

_running: dict[int, asyncio.Task] = {}
# Started again once the running one is done (a list linked while the first sync ran).
_again: set[int] = set()


def running(user_id: int) -> bool:
    return user_id in _running


def start(user_id: int) -> asyncio.Task:
    """Sync a user's lists in the background. When a sync is running already, another one
    follows it (the lists may have changed meanwhile, e.g. a second one linked)."""
    if user_id in _running:
        _again.add(user_id)
        return _running[user_id]
    task = asyncio.create_task(_run(user_id))
    _running[user_id] = task

    def done(_: asyncio.Task) -> None:
        _running.pop(user_id, None)
        if user_id in _again:
            _again.discard(user_id)
            start(user_id)

    task.add_done_callback(done)
    return task


async def _run(user_id: int) -> dict[str, Any] | None:
    from app.services.sync import sync_user  # sync imports most services

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if user is None or user.is_guest:
            return None
        try:
            result = await sync_user(db, user)
        except Exception:
            log.exception("Background sync of user %s failed", user_id)
            raise
    stats_jobs.clear_failure(user_id)
    stats_jobs.start(user_id)
    return result


async def wait(user_id: int) -> dict[str, Any] | None:
    """The result of the running sync (None when there's none)."""
    task = _running.get(user_id)
    return await task if task is not None else None


async def wait_idle() -> None:
    """Wait for running syncs (tests, shutdown)."""
    while _running:
        await asyncio.gather(*list(_running.values()), return_exceptions=True)
