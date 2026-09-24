"""Scraping logic for aniworld.to."""
from __future__ import annotations

import asyncio
import html
import re
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://aniworld.to"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# data-lang-key values used on episode pages
LANG_KEYS = {
    "1": "German Dub",
    "2": "English Sub",
    "3": "German Sub",
}

# flag icons used in the season episode table
FLAG_LANGS = {
    "german.svg": "German Dub",
    "japanese-german.svg": "German Sub",
    "japanese-english.svg": "English Sub",
    "english.svg": "English Dub",
}

SEASON_RE = re.compile(r"^/anime/stream/([^/]+)/(staffel-(\d+)|filme)/?$")
SERIES_RE = re.compile(r"^/anime/stream/([^/]+)/?$")


class _TTLCache:
    """Tiny in-memory cache so repeated calls don't hammer the site."""

    def __init__(self, ttl: int = 900):
        self.ttl = ttl
        self._data: dict[str, tuple[float, Any]] = {}

    def get(self, key: str):
        hit = self._data.get(key)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        return None

    def set(self, key: str, value: Any):
        self._data[key] = (time.time(), value)


class AniWorldScraper:
    def __init__(self, max_concurrency: int = 5, cache_ttl: int = 900):
        self.client = httpx.AsyncClient(
            base_url=BASE_URL, headers=HEADERS, follow_redirects=True, timeout=20
        )
        self.sem = asyncio.Semaphore(max_concurrency)
        self.cache = _TTLCache(cache_ttl)

    async def close(self):
        await self.client.aclose()

    # ------------------------------------------------------------------ http
    async def _get_html(self, path: str) -> BeautifulSoup:
        cached = self.cache.get(path)
        if cached is None:
            async with self.sem:
                r = await self.client.get(path)
            r.raise_for_status()
            cached = r.text
            self.cache.set(path, cached)
        return BeautifulSoup(cached, "html.parser")

    # ---------------------------------------------------------------- search
    async def search(self, query: str) -> list[dict]:
        async with self.sem:
            r = await self.client.post(
                "/ajax/search",
                data={"keyword": query},
                headers={"X-Requested-With": "XMLHttpRequest", "Referer": BASE_URL + "/"},
            )
        r.raise_for_status()
        results = []
        seen = set()
        for item in r.json():
            link = item.get("link", "")
            m = SERIES_RE.match(link)
            if not m or m.group(1) in seen:
                continue  # skip seasons/episodes/support pages
            seen.add(m.group(1))
            results.append(
                {
                    "slug": m.group(1),
                    "title": _strip_tags(item.get("title", "")),
                    "description": _strip_tags(item.get("description", "")),
                    "url": BASE_URL + link,
                }
            )
        return results

    # ---------------------------------------------------------------- series
    async def get_series(self, slug: str) -> dict:
        soup = await self._get_html(f"/anime/stream/{slug}")
        title_el = soup.select_one("div.series-title h1 span") or soup.select_one("h1")
        desc_el = soup.select_one("p.seri_des")

        seasons: list[dict] = []
        seen = set()
        for a in soup.select("#stream a[href]"):
            m = SEASON_RE.match(a["href"])
            if not m or m.group(1) != slug or m.group(2) in seen:
                continue
            seen.add(m.group(2))
            is_movies = m.group(2) == "filme"
            seasons.append(
                {
                    "season": 0 if is_movies else int(m.group(3)),
                    "name": "Movies" if is_movies else f"Season {m.group(3)}",
                    "path": a["href"],
                }
            )
        seasons.sort(key=lambda s: (s["season"] == 0, s["season"]))

        return {
            "slug": slug,
            "title": title_el.get_text(strip=True) if title_el else slug,
            "description": (desc_el.get("data-full-description") or desc_el.get_text(strip=True))
            if desc_el
            else None,
            "url": f"{BASE_URL}/anime/stream/{slug}",
            "seasons": seasons,
        }

    # ---------------------------------------------------------------- season
    async def get_season(self, slug: str, season: int) -> list[dict]:
        season_part = "filme" if season == 0 else f"staffel-{season}"
        soup = await self._get_html(f"/anime/stream/{slug}/{season_part}")

        episodes = []
        for row in soup.select("table.seasonEpisodesList tbody tr"):
            link = row.select_one("a[href]")
            if not link:
                continue
            href = link["href"]
            num_match = re.search(r"/(?:episode|film)-(\d+)$", href)
            title_cell = row.select_one("td.seasonEpisodeTitle")
            de_title = title_cell.select_one("strong") if title_cell else None
            en_title = title_cell.select_one("span") if title_cell else None

            hosters = sorted(
                {i.get("title", "").replace("Hoster", "").strip() for i in row.select("i.icon[title]")}
                - {""}
            )
            languages = sorted(
                {
                    FLAG_LANGS.get(img.get("src", "").rsplit("/", 1)[-1], img.get("title", "unknown"))
                    for img in row.select("img.flag")
                }
            )
            episodes.append(
                {
                    "episode": int(num_match.group(1)) if num_match else None,
                    "title_de": de_title.get_text(strip=True) or None if de_title else None,
                    "title_en": en_title.get_text(strip=True) or None if en_title else None,
                    "url": BASE_URL + href,
                    "path": href,
                    "hosters": hosters,
                    "languages": languages,
                }
            )
        return episodes

    # --------------------------------------------------------------- episode
    async def get_streams(self, path: str) -> dict:
        """Return the available streams of one episode page, grouped by language."""
        soup = await self._get_html(path)

        # language names as the page labels them (fallback: static map)
        lang_names = dict(LANG_KEYS)
        for img in soup.select(".changeLanguageBox img[data-lang-key]"):
            key = img["data-lang-key"]
            src = img.get("src", "").rsplit("/", 1)[-1]
            lang_names[key] = FLAG_LANGS.get(src) or LANG_KEYS.get(key) or img.get("title", key)

        streams = []
        for li in soup.select("li[data-link-target]"):
            key = li.get("data-lang-key", "")
            hoster_el = li.select_one("h4")
            streams.append(
                {
                    "hoster": hoster_el.get_text(strip=True) if hoster_el else None,
                    "language": lang_names.get(key, key),
                    "language_key": key,
                    "link_id": li.get("data-link-id"),
                    "url": BASE_URL + li["data-link-target"],
                }
            )

        by_language: dict[str, list[dict]] = {}
        for s in streams:
            by_language.setdefault(s["language"], []).append(
                {"hoster": s["hoster"], "url": s["url"], "link_id": s["link_id"]}
            )
        return {"languages": sorted(by_language), "streams": by_language}

    # ------------------------------------------------------------ everything
    async def get_full(self, slug: str, season: int | None = None, with_streams: bool = True) -> dict:
        series = await self.get_series(slug)
        wanted = [s for s in series["seasons"] if season is None or s["season"] == season]

        async def load_season(s: dict):
            eps = await self.get_season(slug, s["season"])
            if with_streams:
                details = await asyncio.gather(
                    *(self.get_streams(e["path"]) for e in eps), return_exceptions=True
                )
                for ep, d in zip(eps, details):
                    if isinstance(d, Exception):
                        ep["error"] = str(d)
                    else:
                        ep["languages"] = d["languages"]
                        ep["streams"] = d["streams"]
            for ep in eps:
                ep.pop("path", None)
            return {"season": s["season"], "name": s["name"], "episodes": eps}

        series["seasons"] = await asyncio.gather(*(load_season(s) for s in wanted))
        return series


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
