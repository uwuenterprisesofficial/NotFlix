import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, OptionalUser
from app.core.cache import redis
from app.models import ListEntry, ProviderMapping, SkipSegment, User
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
    CachedResolutionOut,
    EpisodeLanguages,
    EpisodeOptionsOut,
    MappingOut,
    PreviewOut,
    ProviderCoverageOut,
    ProviderScanOut,
    ResolvedOut,
    ShowStreamsOut,
    SkipSegmentOut,
    SourceOptionOut,
    StreamOut,
    SubtitleOut,
)
from app.services import airing as airing_info
from app.services import catalog, source_scan
from app.services.mappings import delete_mapping, save_mapping
from app.services.proxy import TOKEN_MAX_AGE_S, proxy_url

log = logging.getLogger(__name__)
# Proxy links handed out now stop working after TOKEN_MAX_AGE_S; clients refetch well before.
PROXY_LINKS_VALID = timedelta(seconds=TOKEN_MAX_AGE_S) - timedelta(hours=1)
# While a scan runs, the browser's copy is incomplete: it asks again this soon.
SCANNING_RECHECK = timedelta(seconds=30)
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


def resolved_out(
    resolved: Resolved, stored: source_scan.StoredResolution | None = None
) -> ResolvedOut:
    """`stored` adds when the links were fetched and until when they can be reused (at most as
    long as the proxy links made here stay valid)."""
    return ResolvedOut(
        resolved_at=stored.resolved_at if stored else None,
        expires_at=(
            min(stored.expires_at, datetime.now(UTC) + PROXY_LINKS_VALID) if stored else None
        ),
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
    # Episodes that haven't aired have no streams yet: they aren't looked for.
    aired = await airing_info.aired_episodes(db, anime)
    if aired == 0:
        return info
    window = source_scan.scan_window(
        min(num_episodes or aired, aired) if aired else num_episodes, around
    )
    if aired:
        window = [ep for ep in window if ep <= aired]
    await source_scan.ensure_scan(info, window, airing, force)
    return info


async def _not_aired(db: DB, anime_id: int, episode: int) -> bool:
    anime = await catalog.get_anime(db, anime_id)
    aired = await airing_info.aired_episodes(db, anime)
    return aired is not None and episode > aired


def _option_out(o: SourceOption) -> SourceOptionOut:
    return SourceOptionOut(
        id=o.id,
        provider=o.provider,
        label=o.label,
        language=o.language,
        resolved=resolved_out(o.resolved) if o.resolved else None,
    )


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
    need a /resolve call. None for an episode that hasn't aired."""
    if await _not_aired(db, anime_id, episode):
        return []
    info = await _start_scan(db, anime_id, user, around=episode)
    names = [p.name for p in providers_base.enabled_providers() if provider in (None, p.name)]
    found = await asyncio.gather(*(_options(info, episode, name) for name in names))
    return [_option_out(o) for options in found for o in options]


@router.get("/streams", response_model=ShowStreamsOut)
async def show_streams(anime_id: int, db: DB, user: OptionalUser, episode: int | None = None):
    """Every cached source of the show and every still-valid resolution, in one response, for
    the browser to keep until `expires_at`. A provider that hasn't covered an episode yet
    (not in its `episodes`, and not failed) is asked through /episodes/{n}/sources."""
    info = await _start_scan(db, anime_id, user, around=episode)
    anime = await catalog.get_anime(db, anime_id)
    airing = anime is None or anime.num_episodes is None or anime.status == "currently_airing"
    names = [p.name for p in providers_base.enabled_providers()]
    scans, options = await source_scan.cached_sources(info.id, names)
    resolutions = await source_scan.cached_resolutions(info.id)

    now = datetime.now(UTC)
    cap = now + PROXY_LINKS_VALID
    scanning = source_scan.scanning(info.id)
    if scanning:
        expires_at = now + SCANNING_RECHECK
    else:
        ttl = source_scan.scan_ttl(airing)
        finished = [s.finished_at for s in scans.values() if s.finished_at]
        expires_at = min([cap, *(f + ttl for f in finished)])
        expires_at = max(expires_at, now + SCANNING_RECHECK)
    return ShowStreamsOut(
        providers=[
            ProviderCoverageOut(
                name=name,
                status=scans[name].status if name in scans else "none",
                episodes=scans[name].episodes if name in scans else [],
            )
            for name in names
        ],
        scanning=scanning,
        expires_at=expires_at,
        episodes=[
            EpisodeOptionsOut(episode=ep, options=[_option_out(o) for o in found])
            for ep, found in sorted(options.items())
        ],
        resolutions=[
            CachedResolutionOut(
                episode=r.episode, option=r.option_id, resolved=resolved_out(r.resolved, r)
            )
            for r in resolutions
        ],
    )


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
async def resolve_source(anime_id: int, episode: int, option: str, db: DB, fresh: bool = False):
    """The option's playable streams: stored ones while they're valid (unless `fresh`, e.g.
    because they stopped working), otherwise asked from the provider and stored."""
    if await _not_aired(db, anime_id, episode):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Episode {episode} hasn't aired yet")
    if not fresh:
        for stored in await source_scan.cached_resolutions(anime_id, episode, option):
            return resolved_out(stored.resolved, stored)
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
    if not resolved.streams:
        return resolved_out(resolved)  # nothing to play; not worth keeping
    stored = await source_scan.store_resolution(anime_id, episode, option, resolved)
    return resolved_out(resolved, stored)


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


PREVIEW_EPISODE = 1
PREVIEW_RESOLVE_TRIES = 2
PREVIEW_MISS_TTL_S = 30 * 60
LANGUAGE_ORDER = {
    "de": ("de-dub", "de-sub", "en-dub", "en-sub", "unknown"),
    "en": ("en-dub", "en-sub", "de-dub", "de-sub", "unknown"),
}


def _direct(resolved: Resolved | None) -> Stream | None:
    return next((s for s in resolved.streams if s.kind == "direct"), None) if resolved else None


@router.get("/preview", response_model=PreviewOut)
async def preview(anime_id: int, db: DB, lang: Literal["de", "en"] = "en"):
    """A direct stream of episode 1 for the hover card, in the UI's language order, starting
    at its opening when that's known. Only sources already found for the episode are used
    (hovering never starts a scan); at most two are resolved, and a show without any isn't
    tried again for half an hour."""
    anime = await catalog.get_anime(db, anime_id)
    if anime is None or await airing_info.aired_episodes(db, anime) == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing has aired")
    episode = PREVIEW_EPISODE
    order = LANGUAGE_ORDER[lang]
    names = [p.name for p in providers_base.enabled_providers()]
    options = [
        o
        for found in await asyncio.gather(
            *(source_scan.cached_options(anime_id, episode, n) for n in names)
        )
        for o in found or []
    ]
    options.sort(key=lambda o: order.index(o.language) if o.language in order else len(order))
    stored = {
        r.option_id: r.resolved for r in await source_scan.cached_resolutions(anime_id, episode)
    }

    chosen: tuple[SourceOption, Resolved, Stream] | None = None
    for o in options:
        resolved = o.resolved or stored.get(o.id)
        if stream := _direct(resolved):
            chosen = (o, resolved, stream)
            break
    miss_key = f"preview:miss:{anime_id}:{lang}"
    if chosen is None and options and not await redis().exists(miss_key):
        info = AnimeInfo.from_model(anime)
        for o in [o for o in options if o.id not in stored][:PREVIEW_RESOLVE_TRIES]:
            try:
                resolved = await resolve_option(info, episode, o.id)
            except Exception as e:
                log.info("Preview of %s: %s failed: %s", anime_id, o.id, e)
                continue
            if resolved.streams:
                await source_scan.store_resolution(anime_id, episode, o.id, resolved)
            if stream := _direct(resolved):
                chosen = (o, resolved, stream)
                break
        if chosen is None:
            await redis().set(miss_key, 1, ex=PREVIEW_MISS_TTL_S)
    if chosen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No direct stream to preview")

    option, resolved, stream = chosen
    opening = next((seg for seg in resolved.segments if seg.kind == "opening"), None)
    start = opening.start_s if opening else None
    if start is None:
        start = await db.scalar(
            select(SkipSegment.start_s).where(
                SkipSegment.anime_id == anime_id,
                SkipSegment.episode == episode,
                SkipSegment.kind == "opening",
            )
        )
    out = stream_out(stream)
    return PreviewOut(
        episode=episode, language=option.language, url=out.url, format=out.format,
        start_s=round(start or 0.0, 1),
    )  # fmt: skip
