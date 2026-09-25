"""German (and some English) sources from animetoast.cc through the bundled AniScraper service.

animetoast has one page per show, season and language ("Naruto Ger Dub", "Naruto Ger Sub"), so a
MAL entry maps to a set of page slugs, one per language. Endpoints used:

    GET /search/titles?q=...&source=animetoast   -> pages with slug, title and language
    GET /animetoast/{slug}                        -> the page's episodes and hosters
    GET /animetoast/{slug}/episode/{e}            -> one episode's hoster embed URLs
"""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.core import http
from app.core.cache import get_json, set_json
from app.providers.aniworld import SCRAPER_LANGUAGES
from app.providers.base import (
    AnimeInfo,
    Found,
    Language,
    ProviderError,
    Resolved,
    SourceOption,
    Stream,
    hoster_direct,
)
from app.services import anilist
from app.services.mappings import get_mapping, save_mapping

SHOW_CACHE_TTL = 10 * 60
GUESS_CACHE_TTL = 10 * 60
RETRY_NOT_FOUND_AFTER = timedelta(days=1)
SEARCH_QUERIES = 3
MIN_TITLE_SIMILARITY = 0.85
LANGUAGE_TAG = re.compile(r"\b(ger(man)?|eng(lish)?)\s*(dub|sub)\b", re.IGNORECASE)


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def base_title(title: str) -> str:
    """ "Naruto Shippuden Ger Dub" -> "narutoshippuden" (the show without its language tag)."""
    return _norm(LANGUAGE_TAG.sub("", title))


def pick_pages(results: list[dict[str, Any]], titles: list[str]) -> list[str]:
    """Slugs of the language variants of the search hit that best matches one of `titles`."""
    wanted = [_norm(t) for t in titles if _norm(t)]
    groups: dict[str, list[str]] = {}
    for r in results:
        if isinstance(r, dict) and r.get("slug") and r.get("title"):
            groups.setdefault(base_title(str(r["title"])), []).append(str(r["slug"]))
    scored = [
        (max(SequenceMatcher(None, base, w).ratio() for w in wanted), base)
        for base in groups
        if base and wanted
    ]
    if not scored:
        return []
    score, base = max(scored)
    return sorted(set(groups[base])) if score >= MIN_TITLE_SIMILARITY else []


class AnimeToastProvider:
    name = "animetoast"
    lists_whole_show = True  # a scan lists every episode in a request or two

    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self._http = http

    async def _api(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Parsed JSON, or None when AniScraper says it doesn't exist (4xx)."""
        client = self._http or http.shared("aniscraper", timeout=httpx.Timeout(60, connect=5))
        resp = await client.get(f"{self.base_url}{path}", params=params)
        if 400 <= resp.status_code < 500:
            return None
        if resp.status_code >= 500:
            raise ProviderError(f"AniScraper {resp.status_code} for {path}: {resp.text[:200]}")
        return resp.json()

    async def _find_pages(self, titles: list[str]) -> list[str]:
        failures = searched = 0
        results: list[dict[str, Any]] = []
        for query in list(dict.fromkeys(t for t in titles if len(t) >= 2))[:SEARCH_QUERIES]:
            try:
                data = await self._api("/search/titles", {"q": query, "source": "animetoast"})
            except ProviderError:
                failures += 1
                continue
            found = data.get("animetoast") if isinstance(data, dict) else data
            if not isinstance(found, list):  # {"error": "..."}: animetoast.cc unreachable
                failures += 1
                continue
            searched += 1
            results += found
        if failures and not searched:
            raise ProviderError("AnimeToast search failed; not remembering the show as missing")
        return pick_pages(results, titles)

    async def locate(self, anime: AnimeInfo) -> tuple[list[str], int] | None:
        """(page slugs, episode offset) of this MAL entry on animetoast, cached per anime."""
        mapping = await get_mapping(anime.id, self.name)
        if mapping is not None and mapping.external_id:
            return mapping.external_id.split(","), mapping.episode_offset
        if mapping is not None and (
            mapping.manual or datetime.now(UTC) - mapping.updated_at < RETRY_NOT_FOUND_AFTER
        ):
            return None
        guess_key = f"{self.name}:guess:{anime.id}"
        if guess := await get_json(guess_key):
            return guess, 0

        # Each season has its own pages, so this entry's own titles are the ones to match.
        titles: list[str] = []
        anilist_ok = True
        try:
            info = await anilist.lookup(anime.id)
            titles += info.titles if info else []
        except anilist.AniListUnavailable:
            anilist_ok = False
        titles += [t for t in (anime.title_en, anime.title) if t]

        pages = await self._find_pages(titles)
        if pages and not anilist_ok:
            await set_json(guess_key, pages, GUESS_CACHE_TTL)
        elif anilist_ok:
            await save_mapping(anime.id, self.name, ",".join(pages) or None)
        return (pages, 0) if pages else None

    async def _page(self, slug: str) -> dict[str, Any] | None:
        """One show page (episodes, language, description), cached."""
        key = f"{self.name}:show:{slug}"
        data = await get_json(key)
        if data is None:
            data = await self._api(f"/animetoast/{quote(slug)}", {"streams": "false"})
            if not data:
                return None
            await set_json(key, data, SHOW_CACHE_TTL)
        return data

    async def description(self, anime: AnimeInfo) -> str | None:
        """The show's German description from its animetoast page (German pages first)."""
        located = await self.locate(anime)
        if located is None:
            return None
        slugs = sorted(located[0], key=lambda s: "ger" not in s.lower())
        for slug in slugs:
            data = await self._page(slug)
            text = str((data or {}).get("description") or "").strip()
            if text:
                return text
        return None

    async def _show(self, slug: str) -> tuple[Language, dict[int, dict[str, Any]]] | None:
        data = await self._page(slug)
        if data is None:
            return None
        language = SCRAPER_LANGUAGES.get(str(data.get("language") or "").lower(), "unknown")
        episodes = {
            e["episode"]: e
            for season in data.get("seasons") or []
            for e in season.get("episodes") or []
            if isinstance(e, dict) and isinstance(e.get("episode"), int)
        }
        return language, episodes

    async def scan(
        self, anime: AnimeInfo, episodes: list[int], found: Found | None = None
    ) -> dict[int, list[SourceOption]]:
        found: dict[int, list[SourceOption]] = {ep: [] for ep in episodes}
        located = await self.locate(anime)
        if located is None:
            return found
        slugs, offset = located
        shows = await asyncio.gather(*(self._show(slug) for slug in slugs))
        for slug, show in zip(slugs, shows, strict=True):
            if show is None:
                continue
            language, by_number = show
            for ep in episodes:
                if entry := by_number.get(ep + offset):
                    hosters = " / ".join(str(h) for h in entry.get("hosters") or [])
                    found[ep].append(
                        SourceOption(
                            id=f"{self.name}:{slug}",
                            provider=self.name,
                            label=hosters or "AnimeToast",
                            language=language,
                        )
                    )
        return found

    async def options(self, anime: AnimeInfo, episode: int) -> list[SourceOption]:
        return (await self.scan(anime, [episode]))[episode]

    async def resolve(self, anime: AnimeInfo, episode: int, key: str) -> Resolved:
        located = await self.locate(anime)
        if located is None or key not in located[0]:
            raise ProviderError(f"Unknown AnimeToast page {key!r}")
        data = await self._api(
            f"/animetoast/{quote(key)}/episode/{episode + located[1]}", {"direct": "true"}
        )
        if not data:
            raise ProviderError("This episode isn't on AnimeToast")
        directs, embeds = [], []
        for group in (data.get("streams") or {}).values():
            for link in group:
                if not isinstance(link, dict):
                    continue
                url = str(link.get("url") or "")
                url = f"https:{url}" if url.startswith("//") else url
                parts = urlsplit(url)
                label = str(link.get("hoster") or parts.hostname or "AnimeToast")
                # A hoster's direct file replaces its embed; hosters without one stay embedded.
                if direct := hoster_direct(link, label):
                    directs.append(direct)
                # Unresolved links still point at animetoast's own ?link= page; skip those.
                elif parts.scheme in ("http", "https") and "animetoast" not in (
                    parts.hostname or ""
                ):
                    embeds.append(Stream(kind="embed", url=url, label=label))
        streams = directs + embeds
        if not streams:
            raise ProviderError("No playable AnimeToast stream for this episode")
        return Resolved(streams=streams)
