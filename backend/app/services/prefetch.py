"""Looking for the streams of the shows on the pages before anyone opens them.

The pages hand over the shows they show (POST /prefetch: the home page's rows, the calendar,
My List, search results), newest first. While nobody needs anything (no show opened, no episode
played or resolved, no preview lingered on for activity.IDLE_AFTER_S, and no scan someone waits
for), they're scanned one show at a time, as background scans: only by providers that never
looked at the show, and holding before every request as soon as anything else goes on (see
source_scan). A show that's opened meanwhile is scanned at full speed.
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
WAIT_POLL_S = 1.0

# anime id -> the episode to scan around; the next one to scan first.
_queue: OrderedDict[int, int] = OrderedDict()
_runner: asyncio.Task | None = None


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


async def _wait_quiet() -> None:
    while not source_scan.quiet():
        await asyncio.sleep(WAIT_POLL_S)


async def _run() -> None:
    from app.api.streams import scan_in_background  # (the API's scan logic)

    while _queue:
        await _wait_quiet()
        if not _queue:
            break
        anime_id, episode = _queue.popitem(last=False)
        if not await redis().set(f"prefetch:done:{anime_id}", 1, ex=DONE_TTL_S, nx=True):
            continue
        try:
            await scan_in_background(anime_id, episode)
            await source_scan.wait_show(anime_id)
        except Exception:
            log.warning("Prefetching anime %s failed", anime_id, exc_info=True)


async def wait_idle() -> None:
    """Wait until the queue is worked off (tests)."""
    while _runner is not None and not _runner.done():
        await asyncio.wait({_runner}, timeout=0.1)


def clear() -> None:
    """Forget the queue (tests)."""
    global _runner
    _queue.clear()
    if _runner is not None:
        _runner.cancel()
    _runner = None
