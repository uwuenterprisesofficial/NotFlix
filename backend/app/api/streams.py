from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models import ProviderMapping
from app.providers.base import (
    AnimeInfo,
    ProviderError,
    Resolved,
    Stream,
    list_options,
    resolve_option,
)
from app.schemas import (
    AniWorldMappingIn,
    MappingOut,
    ResolvedOut,
    SkipSegmentOut,
    SourceOptionOut,
    StreamOut,
    SubtitleOut,
)
from app.services import catalog
from app.services.mappings import delete_mapping, save_mapping
from app.services.proxy import proxy_url

router = APIRouter(prefix="/anime/{anime_id}", tags=["streams"])


def stream_out(stream: Stream) -> StreamOut:
    url = stream.url
    # hls.js needs CORS on every request and some hosts need a Referer; relay those.
    if stream.kind == "direct" and (stream.format == "hls" or stream.headers):
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


@router.get("/episodes/{episode}/sources", response_model=list[SourceOptionOut])
async def episode_sources(anime_id: int, episode: int, db: DB):
    """Every way to watch this episode. Options without `resolved` need a /resolve call."""
    options = await list_options(await _anime_info(db, anime_id), episode)
    return [
        SourceOptionOut(
            id=o.id,
            provider=o.provider,
            label=o.label,
            language=o.language,
            resolved=resolved_out(o.resolved) if o.resolved else None,
        )
        for o in options
    ]


@router.get("/episodes/{episode}/resolve", response_model=ResolvedOut)
async def resolve_source(anime_id: int, episode: int, option: str, db: DB):
    try:
        resolved = await resolve_option(await _anime_info(db, anime_id), episode, option)
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


@router.delete("/mappings/aniworld", status_code=status.HTTP_204_NO_CONTENT)
async def reset_aniworld_mapping(anime_id: int, user: CurrentUser):
    """Forget the mapping so it is detected again on the next request."""
    await delete_mapping(anime_id, "aniworld")
