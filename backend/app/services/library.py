"""The shared stream library: the sources found for a show's episodes, shared between servers
so a show is only looked up once for everyone.

Every server keeps what its own scans find in `shared_sources` and lists it at /library. A
server with an upstream (the desktop app's built-in server in hybrid mode: it finds and plays
streams on the PC, everything else is the online server's) instead
- gets its show data from the upstream (it has no MyAnimeList keys of its own),
- imports what the upstream's library knows about a show before scanning it, so it only looks
  for what nobody has found yet (or what has gone stale), and
- sends what it finds to the upstream's library.

Options are shared without their resolved links (those expire and can be bound to the IP that
fetched them), except embed pages, which stay put. They are kept per provider *and* the way it
gets them (e.g. AniWorld through AniScraper or from the site), because option ids only mean
something to the same kind of provider.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from fastapi.encoders import jsonable_encoder
from sqlalchemy import DateTime, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import http as shared_http
from app.core.api_key import HEADER as API_KEY_HEADER
from app.core.cache import redis
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models import Anime, SharedSource
from app.providers import base as providers_base
from app.providers.base import (
    Language,
    SourceOption,
    StreamProvider,
    resolved_from_json,
    resolved_to_json,
)
from app.services import source_scan

log = logging.getLogger(__name__)

# Local files aren't anyone else's.
NOT_SHARED = frozenset({"database"})
# A show's library is imported from the upstream at most this often (scans in between are the
# app's own, and shared as they go).
PULL_EVERY_S = 15 * 60
# The upstream's show data is used for this long before it's asked again.
ANIME_FRESH_S = 24 * 3600
ANIME_MISSING_S = 10 * 60
UPSTREAM_TIMEOUT = httpx.Timeout(8, connect=3)

_pushing: set[asyncio.Task] = set()


def upstream() -> tuple[str, str] | None:
    """The upstream server's URL and API key, when this server has one."""
    s = get_settings()
    return (s.upstream_url.rstrip("/"), s.upstream_api_key) if s.upstream_url else None


def _client() -> httpx.AsyncClient:
    return shared_http.shared("upstream", timeout=UPSTREAM_TIMEOUT)


async def _upstream_get(path: str) -> httpx.Response:
    url, key = cast(tuple[str, str], upstream())
    return await _client().get(f"{url}{path}", headers={API_KEY_HEADER: key})


def source_of(provider: StreamProvider) -> str:
    return f"{provider.name}/{type(provider).__name__}"


def _shared_providers() -> dict[str, StreamProvider]:
    """This server's providers that share, by their library source."""
    return {source_of(p): p for p in providers_base.enabled_providers() if p.name not in NOT_SHARED}


def option_json(option: SourceOption) -> dict[str, Any]:
    found: dict[str, Any] = {"id": option.id, "label": option.label, "language": option.language}
    if option.resolved and all(s.kind == "embed" for s in option.resolved.streams):
        found["resolved"] = resolved_to_json(option.resolved)
    return found


def option_from_json(data: dict[str, Any], provider: str) -> SourceOption:
    resolved = data.get("resolved")
    return SourceOption(
        id=data["id"],
        provider=provider,
        label=data["label"],
        language=cast(Language, data["language"]),
        resolved=resolved_from_json(resolved) if resolved else None,
    )


# --- What this server shares --------------------------------------------------------------


async def save(anime_id: int, source: str, episodes: dict[int, list[dict[str, Any]]]) -> None:
    """Store episodes' sources in this server's library (newer ones replace older ones)."""
    if not episodes:
        return
    now = datetime.now(UTC)
    rows = [
        {"anime_id": anime_id, "source": source, "episode": ep, "options": options,
         "updated_at": now}
        for ep, options in episodes.items()
    ]  # fmt: skip
    stmt = insert(SharedSource).values(rows)
    async with AsyncSessionLocal() as db:
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["anime_id", "source", "episode"],
                set_={"options": stmt.excluded.options, "updated_at": stmt.excluded.updated_at},
            )
        )
        await db.commit()


async def _push(anime_id: int, source: str, episodes: dict[int, list[dict[str, Any]]]) -> None:
    url, key = cast(tuple[str, str], upstream())
    body = {
        "anime_id": anime_id,
        "source": source,
        "episodes": [{"episode": ep, "options": o} for ep, o in sorted(episodes.items())],
    }
    try:
        resp = await _client().post(
            f"{url}/library/sources", json=body, headers={API_KEY_HEADER: key}
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        log.info("Sharing %s of anime %s with %s failed: %s", source, anime_id, url, e)
    except Exception:
        log.warning("Sharing %s of anime %s with %s failed", source, anime_id, url, exc_info=True)


async def record(anime_id: int, provider: str, results: dict[int, list[SourceOption]]) -> None:
    """What a scan (or a live lookup) found: into the library, the upstream's when there is one
    (sent in the background)."""
    found = next((p for p in _shared_providers().values() if p.name == provider), None)
    if found is None or not results:
        return
    source = source_of(found)
    episodes = {ep: [option_json(o) for o in options] for ep, options in results.items()}
    if upstream() is None:
        await save(anime_id, source, episodes)
        return
    task = asyncio.create_task(_push(anime_id, source, episodes))
    _pushing.add(task)
    task.add_done_callback(_pushing.discard)


async def wait_idle() -> None:
    """Wait for running uploads (tests, shutdown)."""
    while _pushing:
        await asyncio.gather(*list(_pushing), return_exceptions=True)


# Per source: episode -> (options, when they were found)
Shared = dict[str, dict[int, tuple[list[dict[str, Any]], datetime]]]


async def local(anime_id: int) -> Shared:
    """This server's library for a show."""
    async with AsyncSessionLocal() as db:
        rows = await db.scalars(select(SharedSource).where(SharedSource.anime_id == anime_id))
        found: Shared = {}
        for r in rows:
            found.setdefault(r.source, {})[r.episode] = (r.options, r.updated_at)
    return found


async def shared(anime_id: int) -> Shared:
    """The library for a show: the upstream's when there is one, else this server's."""
    if upstream() is None:
        return await local(anime_id)
    resp = await _upstream_get(f"/library/sources/{anime_id}")
    resp.raise_for_status()
    found: Shared = {}
    for entry in resp.json():
        found[entry["source"]] = {
            e["episode"]: (e["options"], datetime.fromisoformat(e["updated_at"]))
            for e in entry["episodes"]
        }
    return found


# --- Using what others found --------------------------------------------------------------


async def pull(anime_id: int) -> None:
    """Import the library's sources for a show into this server's cache (see source_scan), so
    a scan only looks for what's missing or stale. Per provider: everything when the library's
    copy is newer than this server's last scan, otherwise just the episodes it hasn't
    covered. At most every PULL_EVERY_S per show; never raises."""
    if not await redis().set(f"library:pulled:{anime_id}", 1, ex=PULL_EVERY_S, nx=True):
        return
    try:
        found = await shared(anime_id)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        log.info("The shared library of anime %s is unavailable: %s", anime_id, e)
        return
    except Exception:  # the library only saves work: never in the way of looking
        log.warning("The shared library of anime %s failed", anime_id, exc_info=True)
        return
    providers = _shared_providers()
    scans = await source_scan.provider_scans(anime_id)
    for source, episodes in found.items():
        provider = providers.get(source)
        if provider is None or not episodes:
            continue
        if source_scan.scanning_provider(anime_id, provider.name):
            continue
        scan = scans.get(provider.name)
        as_of = min(at for _, at in episodes.values())
        mine = scan.finished_at if scan is not None and scan.status == "done" else None
        newer = mine is None or mine < as_of
        take = {
            ep: [option_from_json(o, provider.name) for o in options]
            for ep, (options, _) in episodes.items()
            if newer or scan is None or ep not in scan.episodes
        }
        if take:
            await source_scan.import_shared(
                anime_id, provider.name, take, finished_at=as_of if newer else None
            )


async def anime(db: AsyncSession, anime_id: int) -> Anime | None:
    """A show from the upstream's catalogue (kept here, asked again after a day)."""
    row = await db.get(Anime, anime_id)
    fresh_key = f"library:anime:{anime_id}"
    if await redis().exists(fresh_key):
        return row
    try:
        resp = await _upstream_get(f"/library/anime/{anime_id}")
        if resp.status_code == 404:
            await redis().set(fresh_key, 1, ex=ANIME_MISSING_S)
            return row
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.info("Anime %s from the upstream failed: %s", anime_id, e)
        return row
    except Exception:  # e.g. a broken TLS setup: what's known here still works
        log.warning("Anime %s from the upstream failed", anime_id, exc_info=True)
        return row
    values = {}
    for column in Anime.__table__.columns:
        if column.name == "updated_at" or column.name not in data:
            continue
        value = data[column.name]
        if isinstance(column.type, DateTime) and isinstance(value, str):
            value = datetime.fromisoformat(value)
        values[column.name] = value
    values["id"] = anime_id
    stmt = insert(Anime).values(values)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["id"], set_={k: v for k, v in values.items() if k != "id"}
        )
    )
    await db.commit()
    await redis().set(fresh_key, 1, ex=ANIME_FRESH_S)
    if row is not None:
        await db.refresh(row)
        return row
    return await db.get(Anime, anime_id)


def anime_json(anime: Anime) -> dict[str, Any]:
    """A catalogue row as the upstream hands it out."""
    return jsonable_encoder(
        {c.name: getattr(anime, c.key) for c in Anime.__mapper__.columns if c.name != "updated_at"}
    )
