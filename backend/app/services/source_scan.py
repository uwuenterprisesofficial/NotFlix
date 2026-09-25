"""Background scans that find every episode's sources and cache them in the database.

Opening a show (or an episode) calls `ensure_scan`, which starts an asyncio task in the API
process for each provider whose cached data is missing, stale or doesn't cover the episodes the
user is near. Reads always come from the cache first; scans only refresh it.

Results are stored as they come in (a few episodes at a time, the ones nearest to the user
first), not when a provider is done, so a long show's first episodes are there in seconds.
Providers that list a whole show in a request or two cover every aired episode; the others
cover a window around the user. A later scan of fresh data only asks for what's missing. Every
stored episode is noted in a change log, so the browser can fetch just what changed.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.core import cache
from app.db.session import AsyncSessionLocal
from app.models import EpisodeSource, ResolvedSource, SourceScan, StreamFailure
from app.providers import base as providers_base
from app.providers.base import (
    AnimeInfo,
    Language,
    Resolved,
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
# Resolved streams: hosters' direct links carry expiring tokens, embed pages stay put.
RESOLVED_DIRECT_TTL = timedelta(hours=3)
RESOLVED_EMBED_TTL = timedelta(days=7)
WINDOW = 60  # episodes per scan
LOOKBEHIND = 5
UNKNOWN_COUNT_LOOKAHEAD = 12
# A scan stores what it found once it has this many episodes, or after this long.
FLUSH_EPISODES = 3
FLUSH_AFTER_S = 1.0
CHANGES_TTL_S = 24 * 3600


@dataclass
class _Scan:
    """A running scan: its task, the episodes it's asked for, and those stored so far."""

    task: asyncio.Task
    episodes: list[int]
    # Goes episode by episode (so progress means something); a listing arrives all at once.
    stepwise: bool = True
    stored: set[int] = field(default_factory=set)


# (anime id, provider) -> the running scan
_running: dict[tuple[int, str], _Scan] = {}


def by_distance(episodes: list[int], around: int) -> list[int]:
    """The episodes nearest to `around` first (the next ones before the previous ones)."""
    return sorted(episodes, key=lambda ep: (abs(ep - around) + (ep < around) * 0.5, ep))


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
        # A failure isn't retried on every page view; asking to refresh retries it right away.
        return force or now - (scan.finished_at or scan.started_at) > FAILED_RETRY_AFTER
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


def _changes_key(anime_id: int) -> str:
    return f"streams:changed:{anime_id}"


def now_ms() -> int:
    return int(time.time() * 1000)


async def _note_changes(anime_id: int, episodes: list[int]) -> None:
    if not episodes:
        return
    stamp = now_ms()
    pipe = cache.redis().pipeline()
    pipe.zadd(_changes_key(anime_id), {str(ep): stamp for ep in episodes})
    pipe.expire(_changes_key(anime_id), CHANGES_TTL_S)
    await pipe.execute()


async def changed_since(anime_id: int, after_ms: int) -> list[int]:
    """Episodes whose cached options were stored at or after this time (ms)."""
    found = await cache.redis().zrangebyscore(_changes_key(anime_id), after_ms, "+inf")
    return sorted(int(ep) for ep in found)


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
        if scan is not None:
            scan.episodes = covered
        await db.commit()
    await _note_changes(anime_id, episodes)
    return covered


class _Writer:
    """Stores a scan's results as they come in: a few episodes at a time, or after a moment."""

    def __init__(self, anime_id: int, provider: str, running: _Scan | None):
        self.anime_id, self.provider, self.running = anime_id, provider, running
        self.pending: dict[int, list[SourceOption]] = {}
        self.written: set[int] = set()
        self.last = time.monotonic()
        self.lock = asyncio.Lock()

    async def add(self, results: dict[int, list[SourceOption]]) -> None:
        self.pending.update(results)
        if len(self.pending) >= FLUSH_EPISODES or time.monotonic() - self.last >= FLUSH_AFTER_S:
            await self.flush()

    async def flush(self) -> None:
        async with self.lock:
            if not self.pending:
                return
            batch, self.pending = self.pending, {}
            # _store also extends the scan's coverage, so these count as checked right away.
            await _store(self.anime_id, self.provider, batch)
            self.written |= set(batch)
            if self.running is not None:
                self.running.stored |= set(batch)
            self.last = time.monotonic()


async def _scan_provider(provider: StreamProvider, anime: AnimeInfo, episodes: list[int]) -> None:
    writer = _Writer(anime.id, provider.name, _running.get((anime.id, provider.name)))
    try:
        results = await providers_base.guarded(
            provider, providers_base.scan(provider, anime, episodes, writer.add), SCAN_TIMEOUT_S
        )
    except Exception as e:
        log.warning("Scan of %s for anime %s failed: %s", provider.name, anime.id, e)
        await writer.flush()  # what was found before the failure is kept
        await _upsert_scan(
            anime.id, provider.name, status="failed", error=str(e)[:500],
            finished_at=datetime.now(UTC),
        )  # fmt: skip
        return
    # What the provider returned without reporting it along the way (e.g. one listing).
    await writer.add({ep: o for ep, o in results.items() if ep not in writer.written})
    await writer.flush()
    await _upsert_scan(
        anime.id, provider.name, status="done", error=None, finished_at=datetime.now(UTC)
    )


def _due(scan: SourceScan | None, wanted: list[int], ttl: timedelta, force: bool) -> list[int]:
    """The episodes a scan should ask for: none when the cache is good; only the missing ones
    when it's fresh but doesn't cover them all; else all of them."""
    if not needs_scan(scan, wanted, ttl, force):
        return []
    fresh = (
        not force
        and scan is not None
        and scan.status == "done"
        and scan.finished_at is not None
        and datetime.now(UTC) - scan.finished_at <= ttl
    )
    if fresh:
        covered = set(scan.episodes)
        return [ep for ep in wanted if ep not in covered]
    return wanted


async def ensure_scan(
    anime: AnimeInfo,
    window: list[int],
    airing: bool,
    force: bool = False,
    whole: list[int] | None = None,
) -> None:
    """Start a background scan for every provider whose cached data isn't good enough. `window`
    is in the order to scan (nearest to the user first); providers that list a whole show get
    `whole` (every aired episode) when it's known."""
    ttl = scan_ttl(airing)
    scans = await _scans(anime.id)
    now = datetime.now(UTC)
    for p in providers_base.enabled_providers():
        key = (anime.id, p.name)
        if key in _running:
            continue
        if force:
            providers_base.clear_backoff(p.name)  # "unreachable" may be over: try it now
        wanted = whole if whole and providers_base.lists_whole_show(p) else window
        previous = scans.get(p.name)
        episodes = _due(previous, wanted, ttl, force)
        if not episodes:
            continue
        await _upsert_scan(
            anime.id, p.name, status="running", started_at=now, error=None,
            episodes=previous.episodes if previous else [],
        )  # fmt: skip
        task = asyncio.create_task(_scan_provider(p, anime, episodes))
        _running[key] = _Scan(task, episodes, stepwise=not providers_base.lists_whole_show(p))
        task.add_done_callback(lambda _, key=key: _running.pop(key, None))


def scan_ttl(airing: bool) -> timedelta:
    return AIRING_TTL if airing else FINISHED_TTL


def running_scan(anime_id: int, provider: str, episode: int) -> _Scan | None:
    """The in-progress scan that will cover this episode, if any."""
    found = _running.get((anime_id, provider))
    return found if found is not None and episode in found.episodes else None


async def wait_for_episode(scan: _Scan, episode: int, timeout: float) -> bool:
    """Wait (at most `timeout`) until a running scan has stored this episode. False when it
    didn't get there in time (or ended without it)."""
    deadline = time.monotonic() + timeout
    while episode not in scan.stored:
        left = deadline - time.monotonic()
        if scan.task.done() or left <= 0:
            return episode in scan.stored
        await asyncio.wait({scan.task}, timeout=min(0.25, left))
    return True


def progress(anime_id: int) -> tuple[int, int] | None:
    """Running episode-by-episode scans of a show: (episodes stored, episodes asked for), or
    None. (A listing arrives all at once: nothing to count.)"""
    scans = [s for key, s in _running.items() if key[0] == anime_id and s.stepwise]
    if not scans:
        return None
    return sum(len(s.stored) for s in scans), sum(len(s.episodes) for s in scans)


def scanning(anime_id: int) -> bool:
    return any(key[0] == anime_id for key in _running)


async def wait_idle() -> None:
    """Wait for running scans (tests, shutdown)."""
    while _running:
        await asyncio.gather(*(s.task for s in list(_running.values())), return_exceptions=True)


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
            delete(ResolvedSource).where(
                ResolvedSource.anime_id == anime_id,
                ResolvedSource.option_id.startswith(f"{provider}:", autoescape=True),
            )
        )
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


async def cached_sources(
    anime_id: int, providers: list[str], episodes: list[int] | None = None
) -> tuple[dict[str, SourceScan], dict[int, list[SourceOption]]]:
    """Every cached option of a show (or of these episodes), per episode, in provider order:
    what the player needs."""
    scans = await _scans(anime_id)
    query = select(EpisodeSource).where(
        EpisodeSource.anime_id == anime_id, EpisodeSource.provider.in_(providers)
    )
    if episodes is not None:
        query = query.where(EpisodeSource.episode.in_(episodes))
    async with AsyncSessionLocal() as db:
        rows = await db.scalars(query.order_by(EpisodeSource.episode, EpisodeSource.position))
        by_episode: dict[int, list[EpisodeSource]] = {}
        for r in rows:
            by_episode.setdefault(r.episode, []).append(r)
    rank = {name: i for i, name in enumerate(providers)}
    options = {
        episode: [
            SourceOption(
                id=r.option_id,
                provider=r.provider,
                label=r.label,
                language=cast(Language, r.language),
                resolved=resolved_from_json(r.resolved) if r.resolved else None,
            )
            for r in sorted(found, key=lambda r: (rank[r.provider], r.position))
        ]
        for episode, found in by_episode.items()
    }
    return scans, options


def resolution_ttl(resolved: Resolved) -> timedelta:
    direct = any(s.kind == "direct" for s in resolved.streams)
    return RESOLVED_DIRECT_TTL if direct else RESOLVED_EMBED_TTL


@dataclass(frozen=True)
class StoredResolution:
    episode: int
    option_id: str
    resolved: Resolved
    resolved_at: datetime
    expires_at: datetime


async def store_resolution(
    anime_id: int, episode: int, option_id: str, resolved: Resolved
) -> StoredResolution:
    """Keep a resolution for the next play (also across restarts)."""
    now = datetime.now(UTC)
    values = {
        "data": resolved_to_json(resolved),
        "resolved_at": now,
        "expires_at": now + resolution_ttl(resolved),
    }
    stmt = insert(ResolvedSource).values(
        anime_id=anime_id, episode=episode, option_id=option_id, **values
    )
    async with AsyncSessionLocal() as db:
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["anime_id", "episode", "option_id"], set_=values
            )
        )
        await db.commit()
    return StoredResolution(episode, option_id, resolved, now, values["expires_at"])


async def cached_resolutions(
    anime_id: int, episode: int | None = None, option_id: str | None = None
) -> list[StoredResolution]:
    """Unexpired resolutions of a show (or of one episode's option); expired ones are dropped."""
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(ResolvedSource).where(
                ResolvedSource.anime_id == anime_id, ResolvedSource.expires_at <= now
            )
        )
        query = select(ResolvedSource).where(ResolvedSource.anime_id == anime_id)
        if episode is not None:
            query = query.where(ResolvedSource.episode == episode)
        if option_id is not None:
            query = query.where(ResolvedSource.option_id == option_id)
        rows = (await db.scalars(query)).all()
        await db.commit()
    return [
        StoredResolution(
            r.episode, r.option_id, resolved_from_json(r.data), r.resolved_at, r.expires_at
        )
        for r in rows
    ]


# Streams that wouldn't play: remembered this long (hosters come back, links get fixed).
FAILURE_TTL = timedelta(days=7)


async def report_failure(anime_id: int, episode: int, option_id: str, stream: str) -> None:
    """A stream wouldn't play: the player tries the others first from now on."""
    now = datetime.now(UTC)
    stmt = insert(StreamFailure).values(
        anime_id=anime_id, episode=episode, option_id=option_id, stream=stream, count=1,
        failed_at=now,
    )  # fmt: skip
    async with AsyncSessionLocal() as db:
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["anime_id", "episode", "option_id", "stream"],
                set_={"count": StreamFailure.count + 1, "failed_at": now},
            )
        )
        await db.commit()


async def clear_failure(anime_id: int, episode: int, option_id: str, stream: str) -> None:
    """It played after all."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(StreamFailure).where(
                StreamFailure.anime_id == anime_id,
                StreamFailure.episode == episode,
                StreamFailure.option_id == option_id,
                StreamFailure.stream == stream,
            )
        )
        await db.commit()


async def failures(anime_id: int) -> list[StreamFailure]:
    """A show's recent stream failures (older ones are forgotten)."""
    since = datetime.now(UTC) - FAILURE_TTL
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(StreamFailure).where(
                StreamFailure.anime_id == anime_id, StreamFailure.failed_at < since
            )
        )
        rows = list(
            await db.scalars(select(StreamFailure).where(StreamFailure.anime_id == anime_id))
        )
        await db.commit()
    return rows
