"""German dub/sub sources from AniWorld. Hoster links are shown as iframe embeds."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from app.core.cache import get_json, set_json
from app.providers.base import (
    AnimeInfo,
    Language,
    ProviderError,
    Resolved,
    SourceOption,
    Stream,
)
from app.services import anilist
from app.services.mappings import get_mapping, save_mapping

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
LINKS_CACHE_TTL = 10 * 60
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

    async def locate(self, anime: AnimeInfo) -> tuple[str, int, int] | None:
        """(slug, season, episode offset) of this MAL entry on AniWorld, cached per anime."""
        mapping = await get_mapping(anime.id, self.name)
        if mapping is not None and mapping.external_id:
            return mapping.external_id, mapping.season or 1, mapping.episode_offset
        if mapping is not None and (
            mapping.manual or datetime.now(UTC) - mapping.updated_at < RETRY_NOT_FOUND_AFTER
        ):
            return None

        info = None
        anilist_ok = True
        try:
            info = await anilist.lookup(anime.id)
        except anilist.AniListUnavailable:
            anilist_ok = False  # Guess from MAL titles and season 1, but don't remember it.
        season = info.season if info else 1
        titles = [*(info.root_titles if info else []), *(info.titles if info else [])]
        titles += [t for t in (anime.title_en, anime.title) if t]

        for slug in slug_candidates(titles):
            html = await self._fetch(self.season_path(slug, season))
            if html and count_episodes(html) > 0:
                if anilist_ok:
                    await save_mapping(anime.id, self.name, slug, season)
                return slug, season, 0
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

    async def options(self, anime: AnimeInfo, episode: int) -> list[SourceOption]:
        return [
            SourceOption(
                id=f"{self.name}:{link.path}",
                provider=self.name,
                label=link.hoster,
                language=link.language,
            )
            for link in await self.episode_links(anime, episode)
        ]

    async def resolve(self, anime: AnimeInfo, episode: int, key: str) -> Resolved:
        if not key.startswith("/") or key.startswith("//"):
            raise ProviderError("Invalid AniWorld link")
        url = f"{self.base_url}{key}"
        # The play link redirects to the hoster's embed page. Resolving it here avoids loading
        # AniWorld inside the iframe; if that fails the iframe can still follow the redirect.
        client = self._client()
        try:
            resp = await client.get(url, follow_redirects=False)
            location = resp.headers.get("location", "")
        except httpx.HTTPError:
            location = ""
        finally:
            if self._http is None:
                await client.aclose()
        target = location if location.startswith("https://") else url
        hoster = urlsplit(target).hostname or "AniWorld"
        return Resolved(streams=[Stream(kind="embed", url=target, label=hoster)])
