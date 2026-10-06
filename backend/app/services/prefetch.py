"""Looking for the streams of the shows on the pages before anyone opens them.

The pages hand over the shows they show (POST /prefetch: the home page's rows, the calendar,
My List, search results), newest first. Whenever a scan worker is free (see
source_scan.SCAN_WORKERS: shows someone waits for come first), the next show is scanned with
background scans: only by providers that never looked at the show, and holding before each
request while the shows someone waits for need every worker. A show that's opened meanwhile is
scanned at full speed.
"""

import asyncio
import logging
from collections import OrderedDict

from app.core.cache import redis
from app.providers import base as providers_base
from app.services import source_scan

log = logging.getLogger(__name__)

MAX_QUEUED = 400
# A show prefetched is left alone for this long (its scans' results last longer than that).
DONE_TTL_S = 6 * 3600
WAIT_POLL_S = 0.5

# anime id -> the episode to scan around; the next one to scan first.
_queue: OrderedDict[int, int] = OrderedDict()
_runner: asyncio.Task | None = None
_active: set[asyncio.Task] = set()  # the background shows being scanned


def enqueue(shows: list[tuple[int, int]]) -> int:
    """Queue shows (anime id, episode), ahead of what was queued before. Returns how many are
    queued now."""
    if not any(p.name != "database" for p in providers_base.enabled_providers()):
        return 0  # nothing to look on (a server that doesn't scrape)
    for anime_id, episode in reversed(shows):
        _queue.pop(anime_id, None)
        _queue[anime_id] = max(1, episode)
        _queue.move_to_end(anime_id, last=False)
    while len(_queue) > MAX_QUEUED:
        _queue.popitem(last=True)
    _start()
    return len(_queue)


def queued() -> list[int]:
    return list(_queue)


def _start() -> None:
    global _runner
    if _queue and (_runner is None or _runner.done()):
        _runner = asyncio.create_task(_run())


async def _scan(anime_id: int, episode: int) -> None:
    from app.api.streams import scan_in_background  # (the API's scan logic)

    try:
        if not await redis().set(f"prefetch:done:{anime_id}", 1, ex=DONE_TTL_S, nx=True):
            return
        await scan_in_background(anime_id, episode)
        await source_scan.wait_show(anime_id)
    except Exception:
        log.warning("Prefetching anime %s failed", anime_id, exc_info=True)


async def _run() -> None:
    """Start the next queued show whenever a worker is free."""
    while _queue or _active:
        if _queue and source_scan.free_workers(len(_active)) > 0:
            anime_id, episode = _queue.popitem(last=False)
            task = asyncio.create_task(_scan(anime_id, episode))
            _active.add(task)
            task.add_done_callback(_active.discard)
            continue
        if _active:
            await asyncio.wait(_active, timeout=WAIT_POLL_S)
        else:
            await asyncio.sleep(WAIT_POLL_S)


async def wait_idle() -> None:
    """Wait until the queue is worked off (tests)."""
    while _runner is not None and not _runner.done():
        await asyncio.wait({_runner}, timeout=0.1)


def clear() -> None:
    """Forget the queue (tests)."""
    global _runner
    _queue.clear()
    for task in [_runner, *_active]:
        if task is not None:
            task.cancel()
    _active.clear()
    _runner = None
