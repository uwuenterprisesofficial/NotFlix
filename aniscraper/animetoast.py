"""Scraping logic for animetoast.cc (WordPress site).

Layout assumed:
  search      /?s=<query>          -> result posts, one per show + language variant
                                      (e.g. "Naruto Ger Dub", "Naruto Ger Sub")
  show page   /<slug>/             -> hoster tabs (ul.nav-tabs a[href="#multi_link_tabN"]),
                                      each tab pane lists episode links (?link=N, "Ep. 1")
  episode     /<slug>/?link=N      -> player with the hoster embed (iframe or link)
  description the show page's post text (German), see parse_description
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from scraper import HEADERS, _TTLCache

BASE_URL = "https://www.animetoast.cc"

LANG_PATTERNS = [
    (re.compile(r"\bger(man)?\s*dub\b", re.I), "German Dub"),
    (re.compile(r"\bger(man)?\s*sub\b", re.I), "German Sub"),
    (re.compile(r"\beng(lish)?\s*dub\b", re.I), "English Dub"),
    (re.compile(r"\beng(lish)?\s*sub\b", re.I), "English Sub"),
]
LANG_STRIP_RE = re.compile(r"\b(ger(man)?|eng(lish)?)\s*(dub|sub)\b", re.I)
EPISODE_RE = re.compile(r"(?:ep(?:isode)?\.?|folge|e)\s*(\d+)", re.I)
# paths that are not show pages
SKIP_PATHS = re.compile(r"^/(category|tag|page|author|wp-|genre|feed|\?)", re.I)


def detect_language(title: str) -> str | None:
    for pattern, name in LANG_PATTERNS:
        if pattern.search(title):
            return name
    return None


DESCRIPTION_SELECTORS = (
    ".entry-content p, .post-content p, .single-content p, .the_content p, "
    ".video-details p, .post-entry p, article p"
)
DESCRIPTION_LABEL_RE = re.compile(r"^(beschreibung|inhalt|handlung|story|plot)\s*:?\s*", re.I)
MIN_DESCRIPTION = 60


def parse_description(soup: BeautifulSoup) -> str | None:
    """The show's description: the longest real paragraph of the post (not the episode link
    lists), else the page's og:description."""
    best = ""
    for p in soup.select(DESCRIPTION_SELECTORS):
        if p.find_parent(class_="tab-pane") or p.find_parent("nav"):
            continue
        text = p.get_text(" ", strip=True)
        links = sum(len(a.get_text(strip=True)) for a in p.select("a"))
        if links > len(text) / 2 or EPISODE_RE.match(text):
            continue  # mostly links: an episode list or navigation
        text = DESCRIPTION_LABEL_RE.sub("", text)
        if len(text) > len(best):
            best = text
    if len(best) < MIN_DESCRIPTION:
        meta = soup.select_one("meta[property='og:description'], meta[name='description']")
        content = (meta.get("content") or "").strip() if meta else ""
        if len(content) > len(best):
            best = content
    return re.sub(r"\s+", " ", best).strip() or None


def base_title(title: str) -> str:
    return re.sub(r"\s+", " ", LANG_STRIP_RE.sub("", title)).strip(" -–|").lower()


class AnimeToastScraper:
    def __init__(self, max_concurrency: int = 5, cache_ttl: int = 900):
        self.client = httpx.AsyncClient(
            base_url=BASE_URL, headers=HEADERS, follow_redirects=True, timeout=20
        )
        self.sem = asyncio.Semaphore(max_concurrency)
        self.cache = _TTLCache(cache_ttl)

    async def close(self):
        await self.client.aclose()

    async def _get_html(self, path: str, params: dict | None = None) -> BeautifulSoup:
        key = path + (str(sorted(params.items())) if params else "")
        cached = self.cache.get(key)
        if cached is None:
            async with self.sem:
                r = await self.client.get(path, params=params)
            r.raise_for_status()
            cached = r.text
            self.cache.set(key, cached)
        return BeautifulSoup(cached, "html.parser")

    # ---------------------------------------------------------------- search
    async def search(self, query: str) -> list[dict]:
        soup = await self._get_html("/", params={"s": query})
        results, seen = [], set()
        candidates = soup.select(
            "div.item-thumbnail a[href], h3.entry-title a[href], h2.entry-title a[href], "
            ".blog-item h3 a[href], article h3 a[href], article h2 a[href]"
        )
        for a in candidates:
            slug = _slug_from_url(a["href"])
            if not slug or slug in seen:
                continue
            title = (a.get("title") or a.get_text(" ", strip=True)).strip()
            if not title:
                continue
            seen.add(slug)
            results.append(
                {
                    "slug": slug,
                    "title": title,
                    "language": detect_language(title),
                    "url": f"{BASE_URL}/{slug}/",
                }
            )
        return results

    # ------------------------------------------------------------ show page
    async def get_show(self, slug: str, with_streams: bool = False) -> dict:
        soup = await self._get_html(f"/{slug}/")
        title_el = soup.select_one("h1.entry-title, h1.light-title, h1")
        title = title_el.get_text(" ", strip=True) if title_el else slug
        language = detect_language(title) or detect_language(slug.replace("-", " ")) or "unknown"

        # tab id -> hoster name
        hoster_names: dict[str, str] = {}
        for a in soup.select("ul.nav-tabs a[href^='#']"):
            hoster_names[a["href"][1:]] = a.get_text(" ", strip=True)

        episodes: dict[int, dict] = {}
        panes = soup.select("div.tab-pane[id]") or [soup]
        for pane in panes:
            hoster = hoster_names.get(pane.get("id", ""), pane.get("id", "unknown"))
            for a in pane.select("a[href*='link=']"):
                m = EPISODE_RE.search(a.get_text(" ", strip=True))
                if not m:
                    continue
                num = int(m.group(1))
                href = a["href"]
                url = href if href.startswith("http") else f"{BASE_URL}/{slug}/{href.lstrip('/')}"
                ep = episodes.setdefault(
                    num, {"episode": num, "hosters": [], "languages": [language], "streams": {language: []}}
                )
                if hoster not in ep["hosters"]:
                    ep["hosters"].append(hoster)
                ep["streams"][language].append({"hoster": hoster, "url": url})

        ep_list = [episodes[k] for k in sorted(episodes)]
        if with_streams:
            await self._resolve_embeds(ep_list)

        return {
            "source": "animetoast",
            "slug": slug,
            "title": title,
            "language": language,
            "url": f"{BASE_URL}/{slug}/",
            "description": parse_description(soup),
            "seasons": [{"season": 1, "name": "Season 1", "episodes": ep_list}],
        }

    async def _resolve_embeds(self, episodes: list[dict]):
        """Replace each ?link=N page URL with the hoster embed URL shown on that page."""
        streams = [s for ep in episodes for lst in ep["streams"].values() for s in lst]

        async def resolve(s: dict):
            try:
                u = urlparse(s["url"])
                soup = await self._get_html(u.path, params=dict(p.split("=", 1) for p in u.query.split("&") if "=" in p))
                player = soup.select_one("#player-embed") or soup
                el = player.select_one("iframe[src]") or player.select_one("a[href][target='_blank']")
                if el:
                    s["page_url"] = s["url"]
                    s["url"] = el.get("src") or el.get("href")
            except httpx.HTTPError as e:
                s["error"] = str(e)

        await asyncio.gather(*(resolve(s) for s in streams))

    async def get_episode(self, slug: str, episode: int) -> dict | None:
        """One episode of a show page with its hoster embed URLs resolved (None if missing)."""
        show = await self.get_show(slug)
        ep = next((e for e in show["seasons"][0]["episodes"] if e["episode"] == episode), None)
        if ep is None:
            return None
        await self._resolve_embeds([ep])
        return {"source": "animetoast", "slug": slug, "language": show["language"], **ep}

    # ----------------------------------------------------------- everything
    async def search_full(self, query: str, with_streams: bool = False) -> dict:
        """Best match plus all its language variants (Ger Dub / Ger Sub / ...)."""
        results = await self.search(query)
        if not results:
            return {"results": [], "other_matches": []}
        best = base_title(results[0]["title"])
        variants = [r for r in results if base_title(r["title"]) == best]
        others = [r for r in results if base_title(r["title"]) != best]
        shows = await asyncio.gather(*(self.get_show(v["slug"], with_streams) for v in variants))
        return {"results": list(shows), "other_matches": others}


def _slug_from_url(href: str) -> str | None:
    u = urlparse(href)
    if u.netloc and "animetoast" not in u.netloc:
        return None
    path = u.path.strip("/")
    if not path or "/" in path or SKIP_PATHS.match("/" + path):
        return None
    return path
