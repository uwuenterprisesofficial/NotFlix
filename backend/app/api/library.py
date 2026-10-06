"""The shared stream library, for other NotFlix servers (desktop apps in hybrid mode): show data
and the sources found for a show's episodes, and where they send what they find. See
services/library.py."""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB
from app.providers.base import ProviderError, resolved_from_json
from app.schemas import SharedEpisodeOut, SharedSourceOut, SharedSourcesIn
from app.services import catalog, library

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/anime/{anime_id}")
async def library_anime(anime_id: int, db: DB) -> dict[str, Any]:
    """A show's catalogue row (fetched from MyAnimeList if this server doesn't have it yet)."""
    anime = await catalog.get_anime(db, anime_id)
    if anime is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown anime")
    return library.anime_json(anime)


@router.get("/sources/{anime_id}", response_model=list[SharedSourceOut])
async def library_sources(anime_id: int):
    """What's known about a show's sources, per provider. Never starts a scan."""
    found = await library.local(anime_id)
    return [
        SharedSourceOut(
            source=source,
            episodes=[
                SharedEpisodeOut(episode=ep, options=options, updated_at=at)
                for ep, (options, at) in sorted(episodes.items())
            ],
        )
        for source, episodes in sorted(found.items())
    ]


def _embeds_only(resolved: dict | None) -> dict | None:
    """Only web embed pages are shared resolved (direct links expire); anything else is dropped."""
    if resolved is None:
        return None
    try:
        parsed = resolved_from_json(resolved)
    except (KeyError, TypeError, ValueError, ProviderError):
        return None
    embeds = all(
        s.kind == "embed" and s.url.startswith(("https://", "http://")) for s in parsed.streams
    )
    return resolved if parsed.streams and embeds else None


@router.post("/sources", status_code=status.HTTP_204_NO_CONTENT)
async def share_sources(body: SharedSourcesIn) -> None:
    """Sources an app found (newer ones replace what's known about these episodes)."""
    provider = body.source.split("/", 1)[0]
    if provider in library.NOT_SHARED:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Not shared")
    episodes: dict[int, list[dict[str, Any]]] = {}
    for entry in body.episodes:
        options = []
        for o in entry.options:
            if not o.id.startswith(f"{provider}:"):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"Option {o.id!r} isn't {provider}'s"
                )
            option: dict[str, Any] = {"id": o.id, "label": o.label, "language": o.language}
            if resolved := _embeds_only(o.resolved):
                option["resolved"] = resolved
            options.append(option)
        episodes[entry.episode] = options
    await library.save(body.anime_id, body.source, episodes)
