"""Background scans that find every episode's sources and cache them in the database.

Opening a show (or an episode) calls `ensure_scan`, which starts an asyncio task in the API
process for each provider whose cached data is missing, stale or doesn't cover the episodes the
user is near. Reads always come from the cache first; scans only refresh it.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.core import cache
from app.db.session import AsyncSessionLocal
from app.models import EpisodeSource, SourceScan
from app.providers import base as providers_base
from app.providers.base import (
    AnimeInfo,
    Language,
    SourceOption,
    StreamProvider,
    resolved_from_json,
    resolved_to_json,
)

log = logging.getLogger(__name__)

AIRING_TTL = timedelta(hours=6)
FINISHED_TTL = timedelta(days=7)
RUNNING_STALE_AFTER = timedelta(minutes=10)  # a scan lost to an API restart
FAILED_RETRY_AFTER = timedelta(minutes=2)
SCAN_TIMEOUT_S = 300
WINDOW = 60  # episodes per scan
LOOKBEHIND = 5
UNKNOWN_COUNT_LOOKAHEAD = 12

# (anime id, provider) -> (task, episodes it covers)
_running: dict[tuple[int, str], tuple[asyncio.Task, list[int]]] = {}


def scan_window(num_episodes: int | None, next_episode: int) -> list[int]:
    """The episodes worth checking: all of a short show, otherwise a window around the user."""
    if num_episodes and num_episodes <= WINDOW:
        return list(range(1, num_episodes + 1))
    start = max(1, next_episode - LOOKBEHIND)
    if num_episodes:
        end = min(start + WINDOW - 1, num_episodes)
        start = max(1, end - WINDOW + 1)
    else:
        end = max(next_episode, UNKNOWN_COUNT_LOOKAHEAD) + UNKNOWN_COUNT_LOOKAHEAD
    return list(range(start, end + 1))


def needs_scan(
    scan: SourceScan | None, window: list[int], ttl: timedelta, force: bool = False
) -> bool:
    now = datetime.now(UTC)
    if scan is None:
        return True
    if scan.status == "running":
        return now - scan.started_at > RUNNING_STALE_AFTER
    if scan.status == "failed":
        return now - (scan.finished_at or scan.started_at) > FAILED_RETRY_AFTER
    if force or not set(window) <= set(scan.episodes):
        return True
    return scan.finished_at is None or now - scan.finished_at > ttl


async def _scans(anime_id: int) -> dict[str, SourceScan]:
    async with AsyncSessionLocal() as db:
        rows = await db.scalars(select(SourceScan).where(SourceScan.anime_id == anime_id))
        return {s.provider: s for s in rows}


async def _upsert_scan(anime_id: int, provider: str, **values) -> None:
    # Postgres checks NOT NULL on the proposed row before ON CONFLICT, so fill the defaults.
    defaults = {"status": "done", "episodes": [], "started_at": datetime.now(UTC)}
    stmt = insert(SourceScan).values(anime_id=anime_id, provider=provider, **{**defaults, **values})
    async with AsyncSessionLocal() as db:
        await db.execute(
            stmt.on_conflict_do_update(index_elements=["anime_id", "provider"], set_=values)
        )
        await db.commit()


async def _store(anime_id: int, provider: str, results: dict[int, list[SourceOption]]) -> list[int]:
    """Replace the cached options of these episodes; returns the scan's new episode coverage."""
    episodes = list(results)
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(EpisodeSource).where(
                EpisodeSource.anime_id == anime_id,
                EpisodeSource.provider == provider,
                EpisodeSource.episode.in_(episodes),
            )
        )
        for episode, options in results.items():
            db.add_all(
                EpisodeSource(
                    anime_id=anime_id,
                    episode=episode,
                    provider=provider,
                    option_id=o.id,
                    label=o.label,
                    language=o.language,
                    resolved=resolved_to_json(o.resolved) if o.resolved else None,
                    position=i,
                )
                for i, o in enumerate(options)
            )
        scan = await db.scalar(
            select(SourceScan).where(
                SourceScan.anime_id == anime_id, SourceScan.provider == provider
            )
        )
        covered = sorted(set(scan.episodes if scan else []) | set(episodes))
        await db.commit()
    return covered


async def _scan_provider(provider: StreamProvider, anime: AnimeInfo, window: list[int]) -> None:
    try:
        results = await providers_base.guarded(
            provider, providers_base.scan(provider, anime, window), SCAN_TIMEOUT_S
        )
    except Exception as e:
        log.warning("Scan of %s for anime %s failed: %s", provider.name, anime.id, e)
        await _upsert_scan(
            anime.id, provider.name, status="failed", error=str(e)[:500],
            finished_at=datetime.now(UTC),
        )  # fmt: skip
        return
    covered = await _store(anime.id, provider.name, results)
    await _upsert_scan(
        anime.id, provider.name, status="done", episodes=covered, error=None,
        finished_at=datetime.now(UTC),
    )  # fmt: skip


async def ensure_scan(
    anime: AnimeInfo, window: list[int], airing: bool, force: bool = False
) -> None:
    """Start a background scan for every provider whose cached data isn't good enough."""
    ttl = AIRING_TTL if airing else FINISHED_TTL
    scans = await _scans(anime.id)
    due = [
        p
        for p in providers_base.enabled_providers()
        if (anime.id, p.name) not in _running and needs_scan(scans.get(p.name), window, ttl, force)
    ]
    now = datetime.now(UTC)
    for p in due:
        previous = scans.get(p.name)
        await _upsert_scan(
            anime.id, p.name, status="running", started_at=now, error=None,
            episodes=previous.episodes if previous else [],
        )  # fmt: skip
        key = (anime.id, p.name)
        task = asyncio.create_task(_scan_provider(p, anime, window))
        _running[key] = (task, window)
        task.add_done_callback(lambda _, key=key: _running.pop(key, None))


def running_scan(anime_id: int, provider: str, episode: int) -> asyncio.Task | None:
    """The in-progress scan that will cover this episode, if any."""
    task, window = _running.get((anime_id, provider), (None, []))
    return task if task is not None and episode in window else None


def scanning(anime_id: int) -> bool:
    return any(key[0] == anime_id for key in _running)


async def wait_idle() -> None:
    """Wait for running scans (tests, shutdown)."""
    while _running:
        await asyncio.gather(*(task for task, _ in list(_running.values())), return_exceptions=True)


async def cached_options(anime_id: int, episode: int, provider: str) -> list[SourceOption] | None:
    """Cached options, or None when this provider hasn't checked this episode yet."""
    scan = (await _scans(anime_id)).get(provider)
    if scan is None or episode not in scan.episodes:
        return None
    async with AsyncSessionLocal() as db:
        rows = await db.scalars(
            select(EpisodeSource)
            .where(
                EpisodeSource.anime_id == anime_id,
                EpisodeSource.episode == episode,
                EpisodeSource.provider == provider,
            )
            .order_by(EpisodeSource.position)
        )
        return [
            SourceOption(
                id=r.option_id,
                provider=r.provider,
                label=r.label,
                language=cast(Language, r.language),
                resolved=resolved_from_json(r.resolved) if r.resolved else None,
            )
            for r in rows
        ]


async def store_episode(
    anime_id: int, provider: str, episode: int, options: list[SourceOption]
) -> None:
    """Cache a live lookup of one episode (e.g. the player opened it before the scan got there)."""
    covered = await _store(anime_id, provider, {episode: options})
    scans = await _scans(anime_id)
    if provider in scans:
        await _upsert_scan(anime_id, provider, episodes=covered)
    else:
        now = datetime.now(UTC)
        await _upsert_scan(
            anime_id, provider, status="done", episodes=covered, started_at=now, finished_at=now
        )


async def forget(anime_id: int, provider: str) -> None:
    """Drop a provider's cache for a show, e.g. after its mapping was corrected."""
    await cache.redis().delete(f"{provider}:guess:{anime_id}")
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(EpisodeSource).where(
                EpisodeSource.anime_id == anime_id, EpisodeSource.provider == provider
            )
        )
        await db.execute(
            delete(SourceScan).where(
                SourceScan.anime_id == anime_id, SourceScan.provider == provider
            )
        )
        await db.commit()


@dataclass(frozen=True)
class Availability:
    languages: dict[int, list[str]]  # episode -> languages with at least one source
    checked: list[int]  # episodes every reachable provider has looked at
    scans: list[SourceScan]


async def availability(anime_id: int) -> Availability:
    enabled = [p.name for p in providers_base.enabled_providers()]
    scans = await _scans(anime_id)
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(EpisodeSource.episode, EpisodeSource.language)
            .where(EpisodeSource.anime_id == anime_id, EpisodeSource.provider.in_(enabled))
            .distinct()
        )
        languages: dict[int, set[str]] = {}
        for episode, language in rows:
            languages.setdefault(episode, set()).add(language)

    # A provider whose last scan failed doesn't hold back "no stream" for the others.
    coverage = [
        set(scans[name].episodes) if name in scans else set()
        for name in enabled
        if not (name in scans and scans[name].status == "failed" and not scans[name].episodes)
    ]
    checked = set.intersection(*coverage) if coverage else set()
    return Availability(
        languages={ep: sorted(langs) for ep, langs in sorted(languages.items())},
        checked=sorted(checked),
        scans=[scans[name] for name in enabled if name in scans],
    )
