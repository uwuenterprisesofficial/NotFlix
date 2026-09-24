"""German dub/sub sources from AniWorld. Hoster links are shown as iframe embeds."""

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.core.cache import get_json, set_json
from app.providers.base import (
    SCAN_CONCURRENCY,
    AnimeInfo,
    Language,
    ProviderError,
    Resolved,
    SourceOption,
    Stream,
    hoster_direct,
)
from app.services import anilist
from app.services.mappings import get_mapping, save_mapping

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
LINKS_CACHE_TTL = 10 * 60
GUESS_CACHE_TTL = 10 * 60
RETRY_NOT_FOUND_AFTER = timedelta(days=1)
MAX_SLUG_CANDIDATES = 8

# Flag icons are named "<audio>" or "<audio>-<subtitles>", e.g. "japanese-german".
FLAG_LANGUAGES: dict[str, Language] = {
    "german": "de-dub",
    "japanese-german": "de-sub",
    "english-german": "de-sub",
    "japanese-english": "en-sub",
    "english": "en-dub",
}
# Older AniWorld markup uses numeric language keys instead of flags.
LANG_KEYS: dict[str, Language] = {"1": "de-dub", "2": "en-sub", "3": "de-sub"}

SEASON_SUFFIX = re.compile(
    r"(\s*[:\-]?\s*\b(season|staffel|part|cour)\s*\d+.*$)"
    r"|(\s+\d+(st|nd|rd|th)\s+season.*$)"
    r"|(\s+(ii|iii|iv|v|2|3|4|5)$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EpisodeLink:
    path: str
    hoster: str
    language: Language


def slugify(title: str) -> str:
    text = unicodedata.normalize("NFKD", title.lower().replace("ß", "ss"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    return re.sub(r"[\s-]+", "-", text).strip("-")


def strip_season(title: str) -> str:
    return SEASON_SUFFIX.sub("", title).strip()


def slug_candidates(titles: list[str]) -> list[str]:
    slugs: list[str] = []
    for title in titles:
        for variant in (title, strip_season(title)):
            slug = slugify(variant)
            if slug and slug not in slugs:
                slugs.append(slug)
    return slugs[:MAX_SLUG_CANDIDATES]


def _language_from_flag(ref: str) -> Language:
    ref = ref.strip()
    if ref.startswith("#icon-flag-"):
        name = ref.removeprefix("#icon-flag-")
    elif ref.startswith("/storage/flags/"):
        name = ref.removeprefix("/storage/flags/").removesuffix(".svg")
    else:
        return "unknown"
    return FLAG_LANGUAGES.get(name.lower(), "unknown")


def _relative(url: str) -> str:
    parts = urlsplit(url)
    return parts.path + (f"?{parts.query}" if parts.query else "")


def parse_episode_links(html: str) -> list[EpisodeLink]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[EpisodeLink] = []

    for button in soup.select("#episode-links .link-box[data-play-url]"):
        use = button.find("use")
        flag = (use.get("href") or use.get("xlink:href") or "") if use else ""
        links.append(
            EpisodeLink(
                path=_relative(str(button["data-play-url"])),
                hoster=str(button.get("data-provider-name") or "Hoster"),
                language=_language_from_flag(str(flag)),
            )
        )

    for item in soup.select("li[data-link-target]"):
        heading = item.find("h4")
        links.append(
            EpisodeLink(
                path=_relative(str(item["data-link-target"])),
                hoster=heading.get_text(strip=True) if heading else "Hoster",
                language=LANG_KEYS.get(str(item.get("data-lang-key")), "unknown"),
            )
        )

    return [link for link in links if link.path.startswith("/")]


def count_episodes(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one(".messageAlert.danger"):
        return 0
    return len(soup.select("tr.episode-row")) or len(
        soup.select("table.seasonEpisodesList tbody tr")
    )


def season_episode_numbers(html: str) -> set[int]:
    """Episode numbers listed on a season page (empty if the layout isn't recognised)."""
    soup = BeautifulSoup(html, "html.parser")
    cells = [
        c.get_text(" ", strip=True) for c in soup.select("tr.episode-row .episode-number-cell")
    ]
    cells += [
        str(m.get("content") or "")
        for m in soup.select("table.seasonEpisodesList meta[itemprop=episodeNumber]")
    ]
    return {int(m.group()) for text in cells if (m := re.search(r"\d+", text))}


class AniWorldProvider:
    name = "aniworld"

    def __init__(self, base_url: str, series_path: str, http: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.series_path = series_path.strip("/")
        self._http = http

    def _client(self) -> httpx.AsyncClient:
        return self._http or httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=5),
            headers={"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"},
        )

    async def _fetch(self, path: str) -> str | None:
        client = self._client()
        try:
            resp = await client.get(f"{self.base_url}{path}", follow_redirects=True)
        finally:
            if self._http is None:
                await client.aclose()
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise ProviderError(f"AniWorld {resp.status_code} for {path}")
        return resp.text

    def season_path(self, slug: str, season: int) -> str:
        return f"/{self.series_path.replace('{slug}', slug)}/staffel-{season}"

    async def candidate_slugs(self, titles: list[str]) -> list[str]:
        """Series slugs to try, best first."""
        return slug_candidates(titles)

    async def season_episodes(self, slug: str, season: int) -> set[int] | None:
        """Episode numbers of a season; None if the series/season doesn't exist. An empty set
        means it exists but the numbers couldn't be read."""
        html = await self._fetch(self.season_path(slug, season))
        if not html or count_episodes(html) == 0:
            return None
        return season_episode_numbers(html)

    async def locate(self, anime: AnimeInfo) -> tuple[str, int, int] | None:
        """(slug, season, episode offset) of this MAL entry on AniWorld, cached per anime."""
        mapping = await get_mapping(anime.id, self.name)
        if mapping is not None and mapping.external_id:
            return mapping.external_id, mapping.season or 1, mapping.episode_offset
        if mapping is not None and (
            mapping.manual or datetime.now(UTC) - mapping.updated_at < RETRY_NOT_FOUND_AFTER
        ):
            return None

        guess_key = f"aniworld:guess:{anime.id}"
        if guess := await get_json(guess_key):
            return guess[0], guess[1], 0

        info = None
        anilist_ok = True
        try:
            info = await anilist.lookup(anime.id)
        except anilist.AniListUnavailable:
            anilist_ok = False  # Guess from MAL titles and season 1, but don't remember it.
        season = info.season if info else 1
        titles = [*(info.root_titles if info else []), *(info.titles if info else [])]
        titles += [t for t in (anime.title_en, anime.title) if t]

        failures = 0
        for slug in await self.candidate_slugs(titles):
            try:
                found = await self.season_episodes(slug, season)
            except ProviderError:
                failures += 1  # A server error isn't evidence that the series doesn't exist.
                continue
            if found is not None:
                if anilist_ok:
                    await save_mapping(anime.id, self.name, slug, season)
                else:  # Not persisted, but don't redo the search for every episode.
                    await set_json(guess_key, [slug, season], GUESS_CACHE_TTL)
                return slug, season, 0
        if failures:
            raise ProviderError("AniWorld lookup failed; not remembering the series as missing")
        if anilist_ok:
            await save_mapping(anime.id, self.name, None)
        return None

    async def episode_links(self, anime: AnimeInfo, episode: int) -> list[EpisodeLink]:
        located = await self.locate(anime)
        if located is None:
            return []
        slug, season, offset = located
        path = f"{self.season_path(slug, season)}/episode-{episode + offset}"
        key = f"aniworld:links:{path}"
        cached = await get_json(key)
        if cached is not None:
            return [EpisodeLink(**link) for link in cached]
        html = await self._fetch(path)
        links = parse_episode_links(html) if html else []
        await set_json(key, [link.__dict__ for link in links], LINKS_CACHE_TTL)
        return links

    def _options(self, links: list[EpisodeLink]) -> list[SourceOption]:
        return [
            SourceOption(
                id=f"{self.name}:{link.path}",
                provider=self.name,
                label=link.hoster,
                language=link.language,
            )
            for link in links
        ]

    async def options(self, anime: AnimeInfo, episode: int) -> list[SourceOption]:
        return self._options(await self.episode_links(anime, episode))

    async def scan(self, anime: AnimeInfo, episodes: list[int]) -> dict[int, list[SourceOption]]:
        """The season page says which episodes exist, so only those episode pages are fetched."""
        found: dict[int, list[SourceOption]] = {ep: [] for ep in episodes}
        located = await self.locate(anime)
        if located is None:
            return found
        slug, season, offset = located
        listed = await self.season_episodes(slug, season) or set()
        wanted = [ep for ep in episodes if not listed or ep + offset in listed]
        limit = asyncio.Semaphore(SCAN_CONCURRENCY)

        async def one(ep: int) -> None:
            async with limit:
                found[ep] = self._options(await self.episode_links(anime, ep))

        await asyncio.gather(*(one(ep) for ep in wanted))
        return found

    async def follow_redirect(self, url: str) -> str:
        """Play links redirect to the hoster's embed page. Resolving that here avoids loading
        AniWorld inside the iframe; if it fails the iframe can still follow the redirect."""
        client = self._client()
        try:
            resp = await client.get(url, follow_redirects=False)
            location = resp.headers.get("location", "")
        except httpx.HTTPError:
            location = ""
        finally:
            if self._http is None:
                await client.aclose()
        return location if location.startswith("https://") else url

    async def resolve(self, anime: AnimeInfo, episode: int, key: str) -> Resolved:
        if not key.startswith("/") or key.startswith("//"):
            raise ProviderError("Invalid AniWorld link")
        target = await self.follow_redirect(f"{self.base_url}{key}")
        hoster = urlsplit(target).hostname or "AniWorld"
        return Resolved(streams=[Stream(kind="embed", url=target, label=hoster)])


def api_language(language: dict | None) -> Language:
    """{"audio": "English", "subtitle": "German"} -> "de-sub" (what counts is the German part)."""
    audio = str((language or {}).get("audio") or "").lower()
    subtitle = str((language or {}).get("subtitle") or "").lower()
    if audio == "german":
        return "de-dub"
    if subtitle == "german":
        return "de-sub"
    if subtitle == "english":
        return "en-sub"
    if audio == "english":
        return "en-dub"
    return "unknown"


class AniWorldApiProvider(AniWorldProvider):
    """AniWorld through a self-hosted API (e.g. one built on SerienStreamAPI) instead of scraping:

    GET /api/series/{title}/episodes/{season}            -> episodes with hosters and languages
    GET /api/series/{title}/episodes/{season}/{episode}  -> the episode's play links

    Scans need one request per season. Options are one per language; the episode's hosters
    (VOE, Doodstream, ...) become that option's streams when it is played.
    """

    def __init__(self, api_url: str, http: httpx.AsyncClient | None = None):
        super().__init__(api_url, "", http)

    async def _api(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Parsed JSON, or None when the API says the series/episode doesn't exist (4xx)."""
        client = self._client()
        try:
            resp = await client.get(f"{self.base_url}{path}", params=params)
        finally:
            if self._http is None:
                await client.aclose()
        if 400 <= resp.status_code < 500:
            return None
        if resp.status_code >= 500:
            raise ProviderError(f"AniWorld API {resp.status_code} for {path}: {resp.text[:200]}")
        return resp.json()

    async def _season(self, slug: str, season: int) -> list[dict[str, Any]] | None:
        key = f"aniworld:api:season:{slug}:{season}"
        cached = await get_json(key)
        if cached is not None:
            return cached
        data = await self._api(f"/api/series/{quote(slug)}/episodes/{season}")
        episodes = [
            e for e in (data if isinstance(data, list) else []) if isinstance(e, dict)
            and isinstance(e.get("number"), int)
        ]  # fmt: skip
        if not episodes:
            return None
        await set_json(key, episodes, LINKS_CACHE_TTL)
        return episodes

    async def season_episodes(self, slug: str, season: int) -> set[int] | None:
        episodes = await self._season(slug, season)
        return {e["number"] for e in episodes} if episodes else None

    def _languages(self, entry: dict[str, Any]) -> list[Language]:
        return [api_language(lang) for lang in entry.get("languages") or []]

    def _episode_options(self, entry: dict[str, Any]) -> list[SourceOption]:
        languages = dict.fromkeys(self._languages(entry))
        label = " / ".join(str(h) for h in entry.get("hosters") or []) or "AniWorld"
        return [
            SourceOption(id=f"{self.name}:{lang}", provider=self.name, label=label, language=lang)
            for lang in languages
        ]

    async def scan(self, anime: AnimeInfo, episodes: list[int]) -> dict[int, list[SourceOption]]:
        found: dict[int, list[SourceOption]] = {ep: [] for ep in episodes}
        located = await self.locate(anime)
        if located is None:
            return found
        slug, season, offset = located
        by_number = {e["number"]: e for e in await self._season(slug, season) or []}
        for ep in episodes:
            if entry := by_number.get(ep + offset):
                found[ep] = self._episode_options(entry)
        return found

    async def options(self, anime: AnimeInfo, episode: int) -> list[SourceOption]:
        return (await self.scan(anime, [episode]))[episode]

    async def resolve(self, anime: AnimeInfo, episode: int, key: str) -> Resolved:
        located = await self.locate(anime)
        if located is None:
            raise ProviderError("This anime isn't mapped to an AniWorld series")
        slug, season, offset = located
        data = await self._api(f"/api/series/{quote(slug)}/episodes/{season}/{episode + offset}")
        streams = [
            s for s in (data or {}).get("streams") or []
            if api_language(s.get("language")) == key
            and urlsplit(str(s.get("videoUrl") or "")).scheme in ("http", "https")
        ]  # fmt: skip
        if not streams:
            raise ProviderError(f"No {key} stream for this episode")
        targets = await asyncio.gather(*(self.follow_redirect(s["videoUrl"]) for s in streams))
        return Resolved(
            streams=[
                Stream(kind="embed", url=target, label=str(s.get("hoster") or "AniWorld"))
                for s, target in zip(streams, targets, strict=True)
            ]
        )


SCRAPER_LANGUAGES: dict[str, Language] = {
    "german dub": "de-dub",
    "german sub": "de-sub",
    "english sub": "en-sub",
    "english dub": "en-dub",
}


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


class AniScraperProvider(AniWorldApiProvider):
    """AniWorld through the bundled AniScraper service (aniscraper/ in this repo):

    GET /search/titles?q=...&source=aniworld           -> matching series slugs
    GET /anime/{slug}?season=N&streams=false           -> the season's episodes and languages
    GET /anime/{slug}/season/{s}/episode/{e}?direct=true
                                                       -> the episode's play links per language,
                                                          with the hoster's `direct_url` if known
    """

    SEARCH_QUERIES = 3

    async def candidate_slugs(self, titles: list[str]) -> list[str]:
        """AniWorld's own search first (exact title matches ranked up), then slug guesses."""
        wanted = {_norm(t) for t in titles}
        found: list[str] = []
        for query in list(dict.fromkeys(strip_season(t) for t in titles))[: self.SEARCH_QUERIES]:
            if len(query) < 2:
                continue
            try:
                data = await self._api("/search/titles", {"q": query, "source": "aniworld"})
            except ProviderError:
                continue  # search is only a shortcut; the guesses below still get tried
            # AniScraper answers {"aniworld": [...]} (or {"aniworld": {"error": ...}}).
            results = data.get("aniworld") if isinstance(data, dict) else data
            if not isinstance(results, list):
                continue
            hits = [r for r in results if isinstance(r, dict) and r.get("slug")]
            hits.sort(key=lambda r: _norm(str(r.get("title") or "")) not in wanted)
            found += [str(r["slug"]) for r in hits]
        return list(dict.fromkeys(found + slug_candidates(titles)))[:MAX_SLUG_CANDIDATES]

    async def _season(self, slug: str, season: int) -> list[dict[str, Any]] | None:
        key = f"aniworld:scraper:season:{slug}:{season}"
        cached = await get_json(key)
        if cached is not None:
            return cached
        data = await self._api(f"/anime/{quote(slug)}", {"season": season, "streams": "false"})
        seasons = (data or {}).get("seasons") or []
        episodes = [
            {**e, "number": e["episode"]}
            for s in seasons if isinstance(s, dict) and s.get("season") == season
            for e in s.get("episodes") or []
            if isinstance(e, dict) and isinstance(e.get("episode"), int)
        ]  # fmt: skip
        if not episodes:
            return None
        await set_json(key, episodes, LINKS_CACHE_TTL)
        return episodes

    def _languages(self, entry: dict[str, Any]) -> list[Language]:
        return [
            SCRAPER_LANGUAGES.get(str(label).lower(), "unknown")
            for label in entry.get("languages") or []
        ]

    async def resolve(self, anime: AnimeInfo, episode: int, key: str) -> Resolved:
        located = await self.locate(anime)
        if located is None:
            raise ProviderError("This anime isn't mapped to an AniWorld series")
        slug, season, offset = located
        data = await self._api(
            f"/anime/{quote(slug)}/season/{season}/episode/{episode + offset}", {"direct": "true"}
        )
        links = [
            link
            for label, group in ((data or {}).get("streams") or {}).items()
            if SCRAPER_LANGUAGES.get(str(label).lower(), "unknown") == key
            for link in group
            if isinstance(link, dict)
        ]
        # A hoster's direct file replaces its embed; hosters without one stay embedded.
        directs = [hoster_direct(link, str(link.get("hoster") or "AniWorld")) for link in links]
        embeds = [
            link
            for link, direct in zip(links, directs, strict=True)
            if direct is None and urlsplit(str(link.get("url") or "")).scheme in ("http", "https")
        ]
        targets = await asyncio.gather(*(self.follow_redirect(link["url"]) for link in embeds))
        streams = [d for d in directs if d] + [
            Stream(kind="embed", url=target, label=str(link.get("hoster") or "AniWorld"))
            for link, target in zip(embeds, targets, strict=True)
        ]
        if not streams:
            raise ProviderError(f"No {key} stream for this episode")
        return Resolved(streams=streams)
