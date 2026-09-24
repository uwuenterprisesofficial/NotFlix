"""Simple REST API around the aniworld.to and animetoast.cc scrapers.

Run:  python main.py   (or: uvicorn main:app --reload --port 9000)
Docs: http://127.0.0.1:9000/docs
"""
import asyncio
from contextlib import asynccontextmanager
from enum import Enum

import httpx
from fastapi import FastAPI, HTTPException, Query

from animetoast import AnimeToastScraper
from scraper import AniWorldScraper

aniworld: AniWorldScraper
animetoast: AnimeToastScraper


class Source(str, Enum):
    aniworld = "aniworld"
    animetoast = "animetoast"
    all = "all"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global aniworld, animetoast
    aniworld = AniWorldScraper()
    animetoast = AnimeToastScraper()
    yield
    await aniworld.close()
    await animetoast.close()


app = FastAPI(title="AniScraper", version="1.1", lifespan=lifespan)


async def _wrap(coro, site: str):
    try:
        return await coro
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        raise HTTPException(404 if code == 404 else 502, f"{site} returned {code}")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Could not reach {site}: {e}")


async def _search_aniworld(q: str, season: int | None, streams: bool) -> dict:
    results = await _wrap(aniworld.search(q), "aniworld.to")
    if not results:
        return {"result": None, "other_matches": []}
    best = await _wrap(
        aniworld.get_full(results[0]["slug"], season=season, with_streams=streams), "aniworld.to"
    )
    best["source"] = "aniworld"
    return {"result": best, "other_matches": results[1:]}


async def _search_animetoast(q: str, streams: bool) -> dict:
    return await _wrap(animetoast.search_full(q, with_streams=streams), "animetoast.cc")


async def _safe(coro):
    """For source=all: one site failing shouldn't break the other."""
    try:
        return await coro
    except HTTPException as e:
        return {"error": e.detail}


@app.get("/search")
async def search(
    q: str = Query(..., min_length=2, description="Title to search for"),
    source: Source = Query(Source.aniworld, description="Which site to search"),
    season: int | None = Query(None, description="aniworld only: just this season (0 = movies)"),
    streams: bool = Query(True, description="Include stream links per episode (slower)"),
):
    """Search a title and return the best match with its episodes, streams and languages.

    - aniworld: `result` = one show with all seasons/languages.
    - animetoast: `results` = one entry per language variant of the best match (Ger Dub, Ger Sub, ...).
      With streams=true the hoster embed URL is resolved for every episode link.
    """
    if source == Source.aniworld:
        data = await _search_aniworld(q, season, streams)
        if not data["result"]:
            raise HTTPException(404, f"No results for '{q}'")
        return {"query": q, **data}

    if source == Source.animetoast:
        data = await _search_animetoast(q, streams)
        if not data["results"]:
            raise HTTPException(404, f"No results for '{q}'")
        return {"query": q, **data}

    aw, at = await asyncio.gather(
        _safe(_search_aniworld(q, season, streams)), _safe(_search_animetoast(q, streams))
    )
    return {"query": q, "aniworld": aw, "animetoast": at}


@app.get("/search/titles")
async def search_titles(
    q: str = Query(..., min_length=2),
    source: Source = Query(Source.all),
):
    """Only the list of matching titles (fast)."""
    out = {}
    if source in (Source.aniworld, Source.all):
        out["aniworld"] = await _safe(_wrap(aniworld.search(q), "aniworld.to"))
    if source in (Source.animetoast, Source.all):
        out["animetoast"] = await _safe(_wrap(animetoast.search(q), "animetoast.cc"))
    return out


# ------------------------------------------------------------------ aniworld
@app.get("/anime/{slug}")
async def anime(
    slug: str,
    season: int | None = Query(None, description="Only this season (0 = movies)"),
    streams: bool = Query(False, description="Include stream links per episode (slower)"),
):
    """aniworld: series info with all seasons and episodes (by slug, e.g. 'one-piece')."""
    return await _wrap(aniworld.get_full(slug, season=season, with_streams=streams), "aniworld.to")


@app.get("/anime/{slug}/season/{season}/episode/{episode}")
async def episode(slug: str, season: int, episode: int):
    """aniworld: streams and languages of a single episode. season=0 means movies."""
    path = (
        f"/anime/stream/{slug}/filme/film-{episode}"
        if season == 0
        else f"/anime/stream/{slug}/staffel-{season}/episode-{episode}"
    )
    data = await _wrap(aniworld.get_streams(path), "aniworld.to")
    return {"slug": slug, "season": season, "episode": episode, **data}


# ---------------------------------------------------------------- animetoast
@app.get("/animetoast/{slug}")
async def animetoast_show(
    slug: str,
    streams: bool = Query(False, description="Resolve hoster embed URLs (one request per link)"),
):
    """animetoast: episodes and hoster links of one show page (slug e.g. 'naruto-ger-dub')."""
    return await _wrap(animetoast.get_show(slug, with_streams=streams), "animetoast.cc")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=9000, reload=True)
