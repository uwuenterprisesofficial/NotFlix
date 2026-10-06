"""Shows related to the ones a user watched (prequels, sequels, films, side stories), for the
My List page: from AniList's public API, which answers for 50 shows per request (MyAnimeList
would need one request per show). Each show's relations are cached for a week; the ones not
cached yet are fetched in the background while the page shows what's known."""

import asyncio
import json
import logging
from typing import Any

import httpx

from app.core import http as shared_http
from app.core.cache import redis
from app.services.anilist import API_URL
from app.services.anilist_account import MEDIA_FIELDS, anime_row

log = logging.getLogger(__name__)

# The relations worth offering: the same story (or around it) in another season or format.
RELATIONS = ("PREQUEL", "SEQUEL", "PARENT", "SIDE_STORY", "SPIN_OFF", "ALTERNATIVE")
BATCH = 50
MAX_SHOWS = 1000  # per user and run: a very long list is covered over several visits
CACHE_TTL_S = 7 * 24 * 3600

# A related show's fields: what the catalogue stores, without the (long) synopsis.
NODE_FIELDS = MEDIA_FIELDS.replace("description(asHtml: false)", "")

QUERY = f"""
query ($ids: [Int]) {{
  Page(page: 1, perPage: {BATCH}) {{
    media(idMal_in: $ids, type: ANIME) {{
      idMal
      relations {{ edges {{ relationType node {{ type {NODE_FIELDS} }} }} }}
    }}
  }}
}}
"""

_running: dict[int, asyncio.Task] = {}


def _key(mal_id: int) -> str:
    return f"related:{mal_id}"


async def cached(ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """The cached relations of these shows: [{"relation", "row"}] (row: the related show as an
    Anime row). Shows without a cache entry are missing from the answer."""
    if not ids:
        return {}
    values = await redis().mget([_key(i) for i in ids])
    return {i: json.loads(v) for i, v in zip(ids, values, strict=True) if v is not None}


def _parse(media: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for edge in (media.get("relations") or {}).get("edges") or []:
        node = edge.get("node") or {}
        relation = edge.get("relationType")
        if relation in RELATIONS and node.get("type") == "ANIME" and node.get("idMal"):
            found.append({"relation": edge["relationType"], "row": anime_row(node)})
    return found


async def fetch(ids: list[int], http: httpx.AsyncClient | None = None) -> None:
    """Fetch and cache the relations of these shows (shows AniList doesn't know are cached as
    having none)."""
    client = http or shared_http.shared("anilist-related", timeout=httpx.Timeout(30, connect=5))
    for start in range(0, len(ids), BATCH):
        batch = ids[start : start + BATCH]
        resp = await client.post(API_URL, json={"query": QUERY, "variables": {"ids": batch}})
        resp.raise_for_status()
        media = ((resp.json().get("data") or {}).get("Page") or {}).get("media") or []
        found = {m["idMal"]: _parse(m) for m in media if m.get("idMal")}
        pipe = redis().pipeline()
        for mal_id in batch:
            pipe.set(_key(mal_id), json.dumps(found.get(mal_id, [])), ex=CACHE_TTL_S)
        await pipe.execute()


def loading(user_id: int) -> bool:
    return user_id in _running


def ensure(user_id: int, missing: list[int]) -> None:
    """Fetch the missing relations in the background (once at a time per user)."""
    if not missing or user_id in _running:
        return

    async def run() -> None:
        try:
            await fetch(missing[:MAX_SHOWS])
        except (httpx.HTTPError, ValueError) as e:
            log.warning("AniList relations for user %s failed: %s", user_id, e)

    task = asyncio.create_task(run())
    _running[user_id] = task
    task.add_done_callback(lambda _: _running.pop(user_id, None))


async def wait_idle() -> None:
    """Wait for running fetches (tests, shutdown)."""
    while _running:
        await asyncio.gather(*list(_running.values()), return_exceptions=True)
