import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.models import Anime

log = logging.getLogger(__name__)

# "<audio>-<dub|sub>": de-dub = German audio, de-sub = Japanese audio with German subtitles, ...
Language = Literal["de-dub", "de-sub", "en-dub", "en-sub", "unknown"]

OPTIONS_TIMEOUT_S = 30
RESOLVE_TIMEOUT_S = 30


class ProviderError(RuntimeError):
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


def enabled_providers() -> list[StreamProvider]:
    from app.core.config import get_settings
    from app.providers.anivexa import AnivexaProvider
    from app.providers.aniworld import AniWorldProvider
    from app.providers.database import DatabaseProvider

    s = get_settings()
    providers: list[StreamProvider] = [DatabaseProvider()]
    if s.aniworld_url:
        providers.append(AniWorldProvider(s.aniworld_url, s.aniworld_series_path))
    if s.anivexa_url:
        providers.append(AnivexaProvider(s.anivexa_url, s.anivexa_providers.split(",")))
    return providers


async def list_options(anime: AnimeInfo, episode: int) -> list[SourceOption]:
    """Ask every provider concurrently; a slow or broken provider only loses its own options."""

    async def run(provider: StreamProvider) -> list[SourceOption]:
        try:
            return await asyncio.wait_for(provider.options(anime, episode), OPTIONS_TIMEOUT_S)
        except Exception:
            log.warning(
                "Provider %s failed for %s E%s", provider.name, anime.id, episode, exc_info=True
            )
            return []

    results = await asyncio.gather(*(run(p) for p in enabled_providers()))
    return [option for found in results for option in found]


async def resolve_option(anime: AnimeInfo, episode: int, option_id: str) -> Resolved:
    name, _, key = option_id.partition(":")
    provider = next((p for p in enabled_providers() if p.name == name), None)
    if provider is None or not key:
        raise ProviderError(f"Unknown source {option_id!r}")
    return await asyncio.wait_for(provider.resolve(anime, episode, key), RESOLVE_TIMEOUT_S)
