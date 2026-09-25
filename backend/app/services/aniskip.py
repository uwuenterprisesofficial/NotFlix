"""AniSkip (https://aniskip.com): crowd-sourced opening/ending times by MAL id and episode.

The fallback while NotFlix's own detection (worker/tasks.py) hasn't found an episode's
opening: shown as "Skip Intro" like detected times, and replaced as soon as the detection
finds the exact times for the stream being played.
"""

import logging
from dataclasses import dataclass

import httpx

from app.core import http as shared_http
from app.core.cache import redis
from app.core.config import get_settings

log = logging.getLogger(__name__)

TIMEOUT_S = 4
MISS_TTL_S = 24 * 3600
# AniSkip's skip types -> ours ("mixed": the opening/ending over story scenes).
_transport: httpx.AsyncBaseTransport | None = None  # tests put a fake AniSkip here
KINDS = {"op": "opening", "mixed-op": "opening", "ed": "ending", "mixed-ed": "ending"}


@dataclass(frozen=True)
class Found:
    kind: str  # opening | ending
    start_s: float
    end_s: float


def enabled() -> bool:
    return bool(get_settings().aniskip_url)


async def skip_times(mal_id: int, episode: int) -> list[Found]:
    """The episode's opening/ending on AniSkip (none when it has none or can't be reached;
    a miss isn't asked again for a day)."""
    if not enabled():
        return []
    miss_key = f"aniskip:miss:{mal_id}:{episode}"
    if await redis().exists(miss_key):
        return []
    url = f"{get_settings().aniskip_url.rstrip('/')}/v2/skip-times/{mal_id}/{episode}"
    params = [("types", t) for t in KINDS] + [("episodeLength", "0")]
    try:
        if _transport is not None:  # tests
            async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=_transport) as client:
                resp = await client.get(url, params=params)
        else:
            resp = await shared_http.shared("aniskip", timeout=TIMEOUT_S).get(url, params=params)
        data = resp.json() if resp.status_code in (200, 404) else None
    except (httpx.HTTPError, ValueError) as e:
        log.info("AniSkip for %s E%s: %s", mal_id, episode, e)
        return []  # unreachable: not remembered as a miss
    if data is None:
        return []
    found: dict[str, Found] = {}
    for result in data.get("results") or []:
        kind = KINDS.get(result.get("skipType"))
        interval = result.get("interval") or {}
        start, end = interval.get("startTime"), interval.get("endTime")
        if kind and kind not in found and start is not None and end is not None and end > start:
            found[kind] = Found(kind, float(start), float(end))
    if not found:
        await redis().set(miss_key, 1, ex=MISS_TTL_S)
    return list(found.values())
