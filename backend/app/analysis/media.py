import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from app.core import cache
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, async_engine
from app.models import Anime
from app.providers.base import AnimeInfo, list_options, resolve_option

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


async def provider_media(anime: AnimeInfo, episode: int) -> Media | None:
    """The first direct (non-iframe) stream any provider offers for this episode."""
    for option in await list_options(anime, episode):
        try:
            resolved = option.resolved or await resolve_option(anime, episode, option.id)
        except Exception:
            continue
        for stream in resolved.streams:
            if stream.kind == "direct":
                return Media(stream.url, stream.headers)
    return None


async def _provider_media_for(anime_id: int, episodes: list[int]) -> dict[int, Media | None]:
    try:
        async with AsyncSessionLocal() as db:
            anime = await db.get(Anime, anime_id)
        info = AnimeInfo.from_model(anime) if anime else AnimeInfo(id=anime_id, title="")
        return {ep: await provider_media(info, ep) for ep in episodes}
    finally:
        # Pooled connections belong to this event loop, which asyncio.run is about to close.
        await async_engine.dispose()
        await cache.close()


def resolve_all(anime_id: int, episodes: list[int]) -> dict[int, Media]:
    """Media for each episode: a local file (<MEDIA_DIR>/<anime_id>/<episode>.<ext>) if present,
    otherwise a direct stream from the providers. Embedded iframes can't be analysed."""
    found = {ep: m for ep in episodes if (m := local_media(anime_id, ep))}
    missing = [ep for ep in episodes if ep not in found]
    if missing:
        for ep, media in asyncio.run(_provider_media_for(anime_id, missing)).items():
            if media is None:
                folder = Path(get_settings().media_dir) / str(anime_id)
                raise MediaNotFound(
                    f"No media for anime {anime_id} episode {ep}: add {folder}/{ep}.mkv "
                    "or a source with a direct stream"
                )
            found[ep] = media
    return found
