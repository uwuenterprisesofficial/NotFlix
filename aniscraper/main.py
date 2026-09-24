"""Simple REST API around the aniworld.to scraper.

Run:  uvicorn main:app --reload
Docs: http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query

from scraper import AniWorldScraper

scraper: AniWorldScraper


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scraper
    scraper = AniWorldScraper()
    yield
    await scraper.close()


app = FastAPI(title="AniScraper", version="1.0", lifespan=lifespan)


async def _wrap(coro):
    try:
        return await coro
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        raise HTTPException(404 if code == 404 else 502, f"aniworld.to returned {code}")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Could not reach aniworld.to: {e}")


@app.get("/search")
async def search(
    q: str = Query(..., min_length=2, description="Title to search for"),
    season: int | None = Query(None, description="Only this season (0 = movies)"),
    streams: bool = Query(True, description="Include stream links per episode (slower)"),
):
    """Search a title and return the best match with its episodes, streams and languages,
    plus the other search hits."""
    results = await _wrap(scraper.search(q))
    if not results:
        raise HTTPException(404, f"No results for '{q}'")
    best = await _wrap(scraper.get_full(results[0]["slug"], season=season, with_streams=streams))
    return {"query": q, "result": best, "other_matches": results[1:]}


@app.get("/search/titles")
async def search_titles(q: str = Query(..., min_length=2)):
    """Only the list of matching titles (fast)."""
    return await _wrap(scraper.search(q))


@app.get("/anime/{slug}")
async def anime(
    slug: str,
    season: int | None = Query(None, description="Only this season (0 = movies)"),
    streams: bool = Query(False, description="Include stream links per episode (slower)"),
):
    """Series info with all seasons and episodes (by slug, e.g. 'one-piece')."""
    return await _wrap(scraper.get_full(slug, season=season, with_streams=streams))


@app.get("/anime/{slug}/season/{season}/episode/{episode}")
async def episode(slug: str, season: int, episode: int):
    """Streams and languages of a single episode. season=0 means movies."""
    path = (
        f"/anime/stream/{slug}/filme/film-{episode}"
        if season == 0
        else f"/anime/stream/{slug}/staffel-{season}/episode-{episode}"
    )
    data = await _wrap(scraper.get_streams(path))
    return {"slug": slug, "season": season, "episode": episode, **data}
