import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from app.core import cache
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, async_engine
from app.models import Anime
from app.providers import base as providers_base
from app.providers.base import (
    AnimeInfo,
    Resolved,
    SourceOption,
    provider_options,
    resolve_option,
)
from app.services import source_scan

MEDIA_EXTENSIONS = (".mkv", ".mp4", ".webm", ".m4a", ".mp3", ".opus", ".aac", ".wav")


class MediaNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Media:
    source: str  # file path or URL ffmpeg can read
    headers: dict[str, str] = field(default_factory=dict)


def local_media(anime_id: int, episode: int) -> Media | None:
    folder = Path(get_settings().media_dir) / str(anime_id)
    for ext in MEDIA_EXTENSIONS:
        candidate = folder / f"{episode}{ext}"
        if candidate.is_file():
            return Media(str(candidate))
    return None


LANGUAGE_LABELS = {
    "de-dub": "German Dub",
    "de-sub": "German Sub",
    "en-sub": "English Sub",
    "en-dub": "English Dub",
    "unknown": "other",
}


async def _options(anime: AnimeInfo, episode: int) -> list[SourceOption]:
    """The episode's sources: cached ones (what the player showed), else asked live."""
    found: list[SourceOption] = []
    for provider in providers_base.enabled_providers():
        cached = await source_scan.cached_options(anime.id, episode, provider.name)
        found += (
            cached if cached is not None else await provider_options(anime, episode, provider.name)
        )
    return found


async def _resolve(anime: AnimeInfo, episode: int, option_id: str, fresh: bool) -> Resolved | None:
    """The option's streams: the stored ones (e.g. what the player just played) unless `fresh`,
    else asked from the provider and stored."""
    if not fresh:
        for stored in await source_scan.cached_resolutions(anime.id, episode, option_id):
            return stored.resolved
    try:
        resolved = await resolve_option(anime, episode, option_id)
    except Exception:
        return None
    if resolved.streams:
        await source_scan.store_resolution(anime.id, episode, option_id, resolved)
    return resolved


async def provider_media(
    anime: AnimeInfo, episode: int, language: str | None, fresh: bool = False
) -> list[Media]:
    """Every direct (non-iframe) stream the providers offer for this episode in `language` (any
    language when None), best first. Embedded players can't be decoded, so they never count."""
    found: list[Media] = []
    for option in await _options(anime, episode):
        if language is not None and option.language != language:
            continue
        resolved = option.resolved or await _resolve(anime, episode, option.id, fresh)
        if resolved:
            found += [Media(s.url, s.headers) for s in resolved.streams if s.kind == "direct"]
    return found


async def _provider_media_for(
    anime_id: int, episodes: list[int], language: str | None, fresh: bool
) -> dict[int, list[Media]]:
    try:
        async with AsyncSessionLocal() as db:
            anime = await db.get(Anime, anime_id)
        info = AnimeInfo.from_model(anime) if anime else AnimeInfo(id=anime_id, title="")
        return {ep: await provider_media(info, ep, language, fresh) for ep in episodes}
    finally:
        # Pooled connections belong to this event loop, which asyncio.run is about to close.
        await async_engine.dispose()
        await cache.close()


def resolve_all(
    anime_id: int, episodes: list[int], language: str | None = None, fresh: bool = False
) -> dict[int, list[Media]]:
    """Candidate media for each episode, to try in order: a local file
    (<MEDIA_DIR>/<anime_id>/<episode>.<ext>) if present, otherwise the direct streams the
    providers offer in `language` (stored links unless `fresh`)."""
    found = {ep: [m] for ep in episodes if (m := local_media(anime_id, ep))}
    missing = [ep for ep in episodes if ep not in found]
    if missing:
        found.update(asyncio.run(_provider_media_for(anime_id, missing, language, fresh)))
    lacking = [ep for ep in episodes if not found.get(ep)]
    if lacking:
        folder = Path(get_settings().media_dir) / str(anime_id)
        where = f" {LANGUAGE_LABELS.get(language, language)}" if language else ""
        raise MediaNotFound(
            f"No direct{where} stream for anime {anime_id} episode"
            f"{'s' if len(lacking) > 1 else ''} {', '.join(map(str, lacking))}: "
            f"embedded players can't be analysed. Add {folder}/<episode>.mkv, "
            "or pick episodes or a language with direct streams."
        )
    return {ep: found[ep] for ep in episodes}
