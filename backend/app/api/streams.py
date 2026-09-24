import asyncio
import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, OptionalUser
from app.models import ListEntry, ProviderMapping, User
from app.providers import base as providers_base
from app.providers.base import (
    OPTIONS_TIMEOUT_S,
    AnimeInfo,
    ProviderError,
    ProviderUnavailable,
    Resolved,
    SourceOption,
    Stream,
    provider_options,
    resolve_option,
)
from app.schemas import (
    AnimeToastMappingIn,
    AniWorldMappingIn,
    AvailabilityOut,
    EpisodeLanguages,
    MappingOut,
    ProviderScanOut,
    ResolvedOut,
    SkipSegmentOut,
    SourceOptionOut,
    StreamOut,
    SubtitleOut,
)
from app.services import catalog, source_scan
from app.services.mappings import delete_mapping, save_mapping
from app.services.proxy import proxy_url

log = logging.getLogger(__name__)
router = APIRouter(prefix="/anime/{anime_id}", tags=["streams"])
providers_router = APIRouter(tags=["streams"])


@providers_router.get("/providers", response_model=list[str])
async def providers():
    """Enabled stream providers; the player loads each one's sources separately."""
    return [p.name for p in providers_base.enabled_providers()]


def stream_out(stream: Stream) -> StreamOut:
    url = stream.url
    # hls.js needs CORS on every request and some hosts need a Referer or the extracting IP;
    # relay those.
    if stream.kind == "direct" and (stream.format == "hls" or stream.headers or stream.relay):
        url = proxy_url(stream.url, stream.headers)
    return StreamOut(
        kind=stream.kind,
        url=url,
        label=stream.label,
        format=stream.format,
        # <track> only loads same-origin subtitles.
        subtitles=[
            SubtitleOut(url=proxy_url(s.url, s.headers), label=s.label, lang=s.lang)
            for s in stream.subtitles
        ],
    )


def resolved_out(resolved: Resolved) -> ResolvedOut:
    return ResolvedOut(
        streams=[stream_out(s) for s in resolved.streams],
        skip_segments=[
            SkipSegmentOut(
                kind=seg.kind,
                start_s=seg.start_s,
                end_s=seg.end_s,
                confidence=1.0,
                source="provider",
            )
            for seg in resolved.segments
        ],
    )


async def _anime_info(db: DB, anime_id: int) -> AnimeInfo:
    anime = await catalog.get_anime(db, anime_id)
    return AnimeInfo.from_model(anime) if anime else AnimeInfo(id=anime_id, title="")


async def _start_scan(
    db: DB, anime_id: int, user: User | None, around: int | None = None, force: bool = False
) -> AnimeInfo:
    """Kick off background scans for the episodes near where the user is."""
    anime = await catalog.get_anime(db, anime_id)
    info = AnimeInfo.from_model(anime) if anime else AnimeInfo(id=anime_id, title="")
    if around is None:
        entry = user and await db.scalar(
            select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id == anime_id)
        )
        around = entry.episodes_watched + 1 if entry else 1
    num_episodes = anime.num_episodes if anime else None
    airing = anime is None or num_episodes is None or anime.status == "currently_airing"
    await source_scan.ensure_scan(
        info, source_scan.scan_window(num_episodes, around), airing, force
    )
    return info


async def _options(info: AnimeInfo, episode: int, provider: str) -> list[SourceOption]:
    """Cached options first; otherwise wait for a running scan, or ask the provider now."""
    cached = await source_scan.cached_options(info.id, episode, provider)
    if cached is not None:
        return cached
    if scan := source_scan.running_scan(info.id, provider, episode):
        try:
            await asyncio.wait_for(asyncio.shield(scan), OPTIONS_TIMEOUT_S)
        except TimeoutError:
            return []
        return await source_scan.cached_options(info.id, episode, provider) or []
    try:
        live = await provider_options(info, episode, provider)
    except Exception as e:
        log.warning("Provider %s failed for %s E%s: %s", provider, info.id, episode, e)
        return []
    await source_scan.store_episode(info.id, provider, episode, live)
    return live


@router.get("/episodes/{episode}/sources", response_model=list[SourceOptionOut])
async def episode_sources(
    anime_id: int, episode: int, db: DB, user: OptionalUser, provider: str | None = None
):
    """Ways to watch this episode (from one provider, or all). Options without `resolved`
    need a /resolve call."""
    info = await _start_scan(db, anime_id, user, around=episode)
    names = [p.name for p in providers_base.enabled_providers() if provider in (None, p.name)]
    found = await asyncio.gather(*(_options(info, episode, name) for name in names))
    return [
        SourceOptionOut(
            id=o.id,
            provider=o.provider,
            label=o.label,
            language=o.language,
            resolved=resolved_out(o.resolved) if o.resolved else None,
        )
        for options in found
        for o in options
    ]


async def _availability(anime_id: int) -> AvailabilityOut:
    found = await source_scan.availability(anime_id)
    return AvailabilityOut(
        episodes=[
            EpisodeLanguages(episode=ep, languages=langs) for ep, langs in found.languages.items()
        ],
        checked=found.checked,
        scans=[ProviderScanOut.model_validate(s) for s in found.scans],
        scanning=source_scan.scanning(anime_id),
    )


@router.get("/availability", response_model=AvailabilityOut)
async def availability(anime_id: int, db: DB, user: OptionalUser):
    """Cached per-episode languages; starts a background scan when the cache needs refreshing."""
    await _start_scan(db, anime_id, user)
    return await _availability(anime_id)


@router.post("/availability/refresh", response_model=AvailabilityOut)
async def refresh_availability(anime_id: int, db: DB, user: CurrentUser):
    await _start_scan(db, anime_id, user, force=True)
    return await _availability(anime_id)


@router.get("/episodes/{episode}/resolve", response_model=ResolvedOut)
async def resolve_source(anime_id: int, episode: int, option: str, db: DB):
    try:
        resolved = await resolve_option(await _anime_info(db, anime_id), episode, option)
    except ProviderUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    except ProviderError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except TimeoutError as e:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Source timed out") from e
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Source failed: {e}") from e
    return resolved_out(resolved)


@router.get("/mappings", response_model=list[MappingOut])
async def mappings(anime_id: int, db: DB):
    rows = await db.scalars(
        select(ProviderMapping)
        .where(ProviderMapping.anime_id == anime_id)
        .order_by(ProviderMapping.provider)
    )
    return rows.all()


@router.put("/mappings/aniworld", status_code=status.HTTP_204_NO_CONTENT)
async def set_aniworld_mapping(anime_id: int, body: AniWorldMappingIn, user: CurrentUser):
    await save_mapping(
        anime_id, "aniworld", body.slug, body.season, body.episode_offset, manual=True
    )
    await source_scan.forget(anime_id, "aniworld")


@router.delete("/mappings/aniworld", status_code=status.HTTP_204_NO_CONTENT)
async def reset_aniworld_mapping(anime_id: int, user: CurrentUser):
    """Forget the mapping so it is detected again on the next request."""
    await delete_mapping(anime_id, "aniworld")
    await source_scan.forget(anime_id, "aniworld")


@router.put("/mappings/animetoast", status_code=status.HTTP_204_NO_CONTENT)
async def set_animetoast_mapping(anime_id: int, body: AnimeToastMappingIn, user: CurrentUser):
    slugs = ",".join(dict.fromkeys(body.slugs))
    await save_mapping(anime_id, "animetoast", slugs, None, body.episode_offset, manual=True)
    await source_scan.forget(anime_id, "animetoast")


@router.delete("/mappings/animetoast", status_code=status.HTTP_204_NO_CONTENT)
async def reset_animetoast_mapping(anime_id: int, user: CurrentUser):
    """Forget the mapping so the pages are searched again on the next request."""
    await delete_mapping(anime_id, "animetoast")
    await source_scan.forget(anime_id, "animetoast")
