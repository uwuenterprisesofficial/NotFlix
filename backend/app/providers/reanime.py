"""English sources from a self-hosted ReAnime.to API (https://github.com/walterwhite-69/ReAnime.to-API).

Only its /search and /servers endpoints are used. The servers are flixcloud embed pages, shown
in an iframe like on reanime.to itself.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from app.core.cache import get_json, set_json
from app.providers.base import (
    AnimeInfo,
    Language,
    ProviderError,
    Resolved,
    Segment,
    SourceOption,
    Stream,
)
from app.services import anilist
from app.services.mappings import get_mapping, save_mapping

SERVERS_CACHE_TTL = 10 * 60
RETRY_NOT_FOUND_AFTER = timedelta(days=1)
AUDIO_LANGUAGE: dict[str, Language] = {"sub": "en-sub", "dub": "en-dub"}


def _items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("data", "results", "anime", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _anilist_id(item: dict[str, Any]) -> int | None:
    for key in ("anilist", "anilist_id", "anilistId"):
        if str(item.get(key) or "").isdigit():
            return int(item[key])
    for url in (item.get("cover_image") or {}).values():
        if isinstance(url, str) and (m := re.search(r"/bx(\d+)-", url)):
            return int(m.group(1))
    return None


def _titles(item: dict[str, Any]) -> list[str]:
    raw = item.get("title") or item.get("name")
    values = raw.values() if isinstance(raw, dict) else [raw]
    return [str(t) for t in values if t]


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def pick_slug(results: list[dict[str, Any]], al_id: int | None, titles: list[str]) -> str | None:
    """Prefer an exact AniList id match; fall back to an exact title match only when the search
    results carry no AniList ids to compare against."""
    candidates = [r for r in results if r.get("slug")]
    if al_id is not None and any(_anilist_id(r) for r in candidates):
        return next((r["slug"] for r in candidates if _anilist_id(r) == al_id), None)
    wanted = {_norm(t) for t in titles if t}
    return next(
        (r["slug"] for r in candidates if any(_norm(t) in wanted for t in _titles(r))), None
    )


def _segment(kind: Literal["opening", "ending"], start: Any, end: Any) -> Segment | None:
    if isinstance(start, int | float) and isinstance(end, int | float) and end > start:
        return Segment(kind=kind, start_s=float(start), end_s=float(end))
    return None


def parse_servers(data: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(audio, server name, embed URL) for every usable server."""
    found = []
    for audio in AUDIO_LANGUAGE:
        for server in data.get(audio) or []:
            url = str(server.get("dataLink") or "")
            if urlsplit(url).scheme == "https":
                found.append((audio, str(server.get("serverName") or "Server"), url))
    return found


def parse_segments(data: dict[str, Any]) -> list[Segment]:
    return [
        seg
        for seg in (
            _segment("opening", data.get("intro_start"), data.get("intro_end")),
            _segment("ending", data.get("outro_start"), data.get("outro_end")),
        )
        if seg
    ]


class ReAnimeProvider:
    name = "reanime"

    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self._http = http

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        client = self._http or httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5))
        try:
            resp = await client.get(f"{self.base_url}{path}", params=params)
        finally:
            if self._http is None:
                await client.aclose()
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise ProviderError(f"ReAnime {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def locate(self, anime: AnimeInfo) -> tuple[str, int | None] | None:
        """(reanime slug, AniList id), cached per anime."""
        try:
            al_id = await anilist.anilist_id(anime.id)
        except anilist.AniListUnavailable:
            al_id = None
        mapping = await get_mapping(anime.id, self.name)
        if mapping is not None and mapping.external_id:
            return mapping.external_id, al_id
        if mapping is not None and datetime.now(UTC) - mapping.updated_at < RETRY_NOT_FOUND_AFTER:
            return None

        titles = [t for t in (anime.title_en, anime.title) if t]
        for query in titles:
            results = _items(await self._get("/search", {"q": query, "limit": 20}))
            if slug := pick_slug(results, al_id, titles):
                await save_mapping(anime.id, self.name, slug)
                return slug, al_id
        await save_mapping(anime.id, self.name, None)
        return None

    async def _servers(self, anime: AnimeInfo, episode: int) -> dict[str, Any] | None:
        located = await self.locate(anime)
        if located is None:
            return None
        slug, al_id = located
        key = f"reanime:servers:{slug}:{episode}"
        cached = await get_json(key)
        if cached is not None:
            return cached
        data = await self._get(
            f"/servers/{slug}/{episode}", {"anilist_id": al_id} if al_id else None
        )
        if data:
            await set_json(key, data, SERVERS_CACHE_TTL)
        return data

    async def options(self, anime: AnimeInfo, episode: int) -> list[SourceOption]:
        data = await self._servers(anime, episode)
        if not data:
            return []
        segments = parse_segments(data)
        return [
            SourceOption(
                id=f"{self.name}:{audio}:{server}",
                provider=self.name,
                label=f"ReAnime {server}",
                language=AUDIO_LANGUAGE[audio],
                resolved=Resolved(
                    streams=[Stream(kind="embed", url=url, label=server)], segments=segments
                ),
            )
            for audio, server, url in parse_servers(data)
        ]

    async def resolve(self, anime: AnimeInfo, episode: int, key: str) -> Resolved:
        for option in await self.options(anime, episode):
            if option.key == key and option.resolved:
                return option.resolved
        raise ProviderError(f"ReAnime source {key!r} not found")
