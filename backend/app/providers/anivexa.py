"""English sources from a self-hosted Anivexa API (https://github.com/walterwhite-69/Anivexa-API)."""

from typing import Any, Literal

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
    Subtitle,
)
from app.services.anilist import anilist_id

EPISODES_CACHE_TTL = 15 * 60
LABELS = {
    "anizone": "AniZone",
    "anikoto": "AniKoto",
    "aniwaves": "AniWaves",
    "animegg": "AnimeGG",
    "anineko": "AniNeko",
    "anidbapp": "AniDB App",
    "anibd": "AniBD",
    "kaa": "KickAssAnime",
    "animedunya": "AnimeDunya",
    "mkissa": "MKissa",
    "reanime": "ReAnime",
    "animeonsen": "AnimeOnsen",
}
RESERVED_KEYS = {"page", "type", "mappings", "_unknownProviders"}
AUDIO_LANGUAGE: dict[str, Language] = {"sub": "en-sub", "dub": "en-dub"}


def available_options(data: dict[str, Any], episode: int) -> list[tuple[str, str]]:
    """(provider, audio) pairs whose episode list contains `episode`."""
    found = []
    for provider, info in data.items():
        if provider in RESERVED_KEYS or not isinstance(info, dict) or "error" in info:
            continue
        for audio, episodes in (info.get("episodes") or {}).items():
            if audio not in AUDIO_LANGUAGE or not isinstance(episodes, list):
                continue
            if any(_as_int(ep.get("number")) == episode for ep in episodes if isinstance(ep, dict)):
                found.append((provider, audio))
    return found


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _headers(stream: dict[str, Any]) -> dict[str, str]:
    headers = {str(k): str(v) for k, v in (stream.get("headers") or {}).items()}
    if stream.get("referer") and not any(k.lower() == "referer" for k in headers):
        headers["Referer"] = str(stream["referer"])
    return headers


def _subtitles(stream: dict[str, Any], headers: dict[str, str]) -> tuple[Subtitle, ...]:
    subs = []
    for sub in stream.get("subtitles") or []:
        if not isinstance(sub, dict):
            continue
        url = sub.get("url") or sub.get("file") or sub.get("src")
        if not url:
            continue
        lang = sub.get("srclang") or sub.get("lang") or sub.get("language")
        label = sub.get("label") or sub.get("title") or lang or "Subtitles"
        subs.append(Subtitle(url=url, label=str(label), lang=lang, headers=headers))
    return tuple(subs)


def _segment(kind: Literal["opening", "ending"], value: Any) -> Segment | None:
    if not isinstance(value, dict):
        return None
    start, end = value.get("start"), value.get("end")
    if not isinstance(start, int | float) or not isinstance(end, int | float) or end <= start:
        return None
    return Segment(kind=kind, start_s=float(start), end_s=float(end))


def parse_watch(data: dict[str, Any], provider: str) -> Resolved:
    streams = []
    for s in data.get("streams") or []:
        url, kind = s.get("url"), s.get("type")
        if not url:
            continue
        label = s.get("server") or LABELS.get(provider, provider)
        if kind == "embed":
            streams.append(Stream(kind="embed", url=url, label=label))
        elif kind in ("hls", "mp4"):
            headers = _headers(s)
            streams.append(
                Stream(
                    kind="direct",
                    url=url,
                    label=label,
                    format="hls" if kind == "hls" else "file",
                    headers=headers,
                    subtitles=_subtitles(s, headers),
                )
            )
        # DASH and other formats aren't supported by the player.

    segments = [
        seg
        for seg in (_segment("opening", data.get("intro")), _segment("ending", data.get("outro")))
        if seg
    ]
    # Direct streams first: only those support skipping and analysis.
    streams.sort(key=lambda st: st.kind != "direct")
    return Resolved(streams=streams, segments=segments)


class AnivexaProvider:
    name = "anivexa"

    def __init__(self, base_url: str, providers: list[str], http: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.providers = [p.strip() for p in providers if p.strip()]
        self._http = http

    async def _get(self, path: str) -> Any:
        client = self._http or httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5))
        try:
            resp = await client.get(f"{self.base_url}{path}")
        finally:
            if self._http is None:
                await client.aclose()
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error")
            except ValueError:
                detail = resp.text[:200]
            raise ProviderError(f"Anivexa {resp.status_code}: {detail}")
        return resp.json()

    async def _episodes(self, al_id: int) -> dict[str, Any]:
        key = f"anivexa:episodes:{al_id}"
        cached = await get_json(key)
        if cached is not None:
            return cached
        data = await self._get(f"/episodes/{'/'.join(self.providers)}/{al_id}?map=false")
        succeeded = any(
            isinstance(v, dict) and "error" not in v
            for k, v in data.items()
            if k not in RESERVED_KEYS
        )
        if succeeded:  # Don't pin a transient outage (e.g. AniList down) for the whole TTL.
            await set_json(key, data, EPISODES_CACHE_TTL)
        return data

    async def options(self, anime: AnimeInfo, episode: int) -> list[SourceOption]:
        al_id = await anilist_id(anime.id)
        if al_id is None or not self.providers:
            return []
        data = await self._episodes(al_id)
        return [
            SourceOption(
                id=f"{self.name}:{provider}:{audio}",
                provider=self.name,
                label=LABELS.get(provider, provider),
                language=AUDIO_LANGUAGE[audio],
            )
            for provider, audio in available_options(data, episode)
        ]

    async def resolve(self, anime: AnimeInfo, episode: int, key: str) -> Resolved:
        provider, _, audio = key.partition(":")
        if provider not in self.providers or audio not in AUDIO_LANGUAGE:
            raise ProviderError(f"Unknown Anivexa source {key!r}")
        al_id = await anilist_id(anime.id)
        if al_id is None:
            raise ProviderError("No AniList id for this anime")
        data = await self._get(f"/watch/{provider}/{al_id}/{audio}/{provider}-{episode}")
        return parse_watch(data, provider)
