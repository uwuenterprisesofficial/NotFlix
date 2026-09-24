import asyncio
import logging
import time
from collections.abc import Awaitable, Coroutine
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar
from urllib.parse import urlsplit

import httpx

from app.models import Anime

log = logging.getLogger(__name__)

# "<audio>-<dub|sub>": de-dub = German audio, de-sub = Japanese audio with German subtitles, ...
Language = Literal["de-dub", "de-sub", "en-dub", "en-sub", "unknown"]

OPTIONS_TIMEOUT_S = 60  # Anivexa's first scrape of a show can take a while
RESOLVE_TIMEOUT_S = 30
UNREACHABLE_BACKOFF_S = 60

_down_until: dict[str, float] = {}
T = TypeVar("T")


class ProviderError(RuntimeError):
    pass


class ProviderUnavailable(ProviderError):
    pass


@dataclass(frozen=True)
class AnimeInfo:
    """Plain snapshot of the anime row, safe to share between concurrently running providers."""

    id: int
    title: str
    title_en: str | None = None
    num_episodes: int | None = None

    @classmethod
    def from_model(cls, anime: Anime) -> "AnimeInfo":
        return cls(anime.id, anime.title, anime.title_en, anime.num_episodes)


@dataclass(frozen=True)
class Subtitle:
    url: str
    label: str
    lang: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Stream:
    kind: Literal["embed", "direct"]
    url: str
    label: str
    format: Literal["hls", "file"] | None = None  # only for direct streams
    headers: dict[str, str] = field(default_factory=dict)  # required by the upstream host
    subtitles: tuple[Subtitle, ...] = ()


@dataclass(frozen=True)
class Segment:
    kind: Literal["opening", "ending"]
    start_s: float
    end_s: float


@dataclass(frozen=True)
class Resolved:
    streams: list[Stream]
    segments: list[Segment] = field(default_factory=list)  # timestamps exact for these streams


@dataclass(frozen=True)
class SourceOption:
    """One way to watch an episode. `resolved` is set when no further request is needed."""

    id: str  # "<provider>:<provider-specific key>"
    provider: str
    label: str
    language: Language
    resolved: Resolved | None = None

    @property
    def key(self) -> str:
        return self.id.split(":", 1)[1]


class StreamProvider(Protocol):
    name: str

    async def options(self, anime: AnimeInfo, episode: int) -> list[SourceOption]: ...

    async def resolve(self, anime: AnimeInfo, episode: int, key: str) -> Resolved: ...


SCAN_CONCURRENCY = 4


async def scan_each_episode(
    provider: StreamProvider, anime: AnimeInfo, episodes: list[int]
) -> dict[int, list[SourceOption]]:
    """Default scan: ask for every episode, a few at a time. Providers that can list many
    episodes in one request implement `scan` themselves."""
    limit = asyncio.Semaphore(SCAN_CONCURRENCY)

    async def one(episode: int) -> tuple[int, list[SourceOption]]:
        async with limit:
            return episode, await provider.options(anime, episode)

    return dict(await asyncio.gather(*(one(ep) for ep in episodes)))


async def scan(
    provider: StreamProvider, anime: AnimeInfo, episodes: list[int]
) -> dict[int, list[SourceOption]]:
    custom = getattr(provider, "scan", None)
    return await (
        custom(anime, episodes) if custom else scan_each_episode(provider, anime, episodes)
    )


def resolved_to_json(resolved: Resolved) -> dict[str, Any]:
    return asdict(resolved)


def resolved_from_json(data: dict[str, Any]) -> Resolved:
    return Resolved(
        streams=[
            Stream(**{**s, "subtitles": tuple(Subtitle(**sub) for sub in s["subtitles"])})
            for s in data["streams"]
        ],
        segments=[Segment(**seg) for seg in data.get("segments", [])],
    )


def enabled_providers() -> list[StreamProvider]:
    from app.core.config import get_settings
    from app.providers.anivexa import AnivexaProvider
    from app.providers.aniworld import AniScraperProvider, AniWorldApiProvider, AniWorldProvider
    from app.providers.database import DatabaseProvider
    from app.providers.reanime import ReAnimeProvider

    s = get_settings()
    providers: list[StreamProvider] = [DatabaseProvider()]
    # AniWorld, in order of preference: the bundled AniScraper service, another self-hosted
    # AniWorld API, or scraping the site from the backend itself.
    if s.aniscraper_url:
        providers.append(AniScraperProvider(s.aniscraper_url))
    elif s.aniworld_api_url:
        providers.append(AniWorldApiProvider(s.aniworld_api_url))
    elif s.aniworld_url:
        providers.append(AniWorldProvider(s.aniworld_url, s.aniworld_series_path))
    if s.reanime_url:
        providers.append(ReAnimeProvider(s.reanime_url))
    if s.anivexa_url:
        providers.append(AnivexaProvider(s.anivexa_url, s.anivexa_providers.split(",")))
    return providers


def unreachable_hint(url: str) -> str:
    parts = urlsplit(url)
    if parts.hostname in {"localhost", "127.0.0.1", "::1"} and Path("/.dockerenv").exists():
        port = f":{parts.port}" if parts.port else ""
        return (
            f" Inside Docker, {parts.hostname} is the backend container itself; "
            f"use http://host.docker.internal{port} to reach a service on the host."
        )
    return ""


async def guarded(provider: StreamProvider, call: Awaitable[T], timeout: float) -> T:
    """Run a provider call; after a connection failure the provider is skipped for a while
    instead of making every page wait for the same failure again."""
    if _down_until.get(provider.name, 0) > time.monotonic():
        if isinstance(call, Coroutine):
            call.close()
        raise ProviderUnavailable(f"{provider.name} is unreachable, retrying shortly")
    try:
        return await asyncio.wait_for(call, timeout)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        _down_until[provider.name] = time.monotonic() + UNREACHABLE_BACKOFF_S
        url = getattr(provider, "base_url", "")
        log.warning(
            "%s is unreachable at %s (%s); skipping it for %ss.%s",
            provider.name,
            url,
            e,
            UNREACHABLE_BACKOFF_S,
            unreachable_hint(url),
        )
        raise ProviderUnavailable(f"{provider.name} is unreachable") from e


async def list_options(
    anime: AnimeInfo, episode: int, provider_name: str | None = None
) -> list[SourceOption]:
    """Ask every provider (or just one) concurrently; a slow or broken provider only loses its
    own options."""

    async def run(provider: StreamProvider) -> list[SourceOption]:
        try:
            return await guarded(provider, provider.options(anime, episode), OPTIONS_TIMEOUT_S)
        except ProviderUnavailable:
            return []
        except ProviderError as e:
            log.warning("Provider %s: %s", provider.name, e)
            return []
        except Exception:
            log.warning(
                "Provider %s failed for %s E%s", provider.name, anime.id, episode, exc_info=True
            )
            return []

    providers = [p for p in enabled_providers() if provider_name in (None, p.name)]
    results = await asyncio.gather(*(run(p) for p in providers))
    return [option for found in results for option in found]


async def provider_options(anime: AnimeInfo, episode: int, name: str) -> list[SourceOption]:
    """One provider's options for an episode; raises instead of returning [] on failure."""
    provider = next((p for p in enabled_providers() if p.name == name), None)
    if provider is None:
        raise ProviderError(f"Unknown provider {name!r}")
    return await guarded(provider, provider.options(anime, episode), OPTIONS_TIMEOUT_S)


async def resolve_option(anime: AnimeInfo, episode: int, option_id: str) -> Resolved:
    name, _, key = option_id.partition(":")
    provider = next((p for p in enabled_providers() if p.name == name), None)
    if provider is None or not key:
        raise ProviderError(f"Unknown source {option_id!r}")
    return await guarded(provider, provider.resolve(anime, episode, key), RESOLVE_TIMEOUT_S)
