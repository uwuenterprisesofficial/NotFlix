"""Jikan (https://jikan.moe), an unofficial read-only MyAnimeList API. Used for what MAL's own
API can't do: listing shows by genre."""

import re
from typing import Any, Literal

import httpx

from app.core.config import get_settings

Order = Literal["score", "popularity", "newest"]
ORDER_BY = {
    "score": ("score", "desc"),
    "popularity": ("members", "desc"),
    "newest": ("start_date", "desc"),
}
PAGE_SIZE = 24

# Jikan writes MAL's enum values the way MAL's site displays them.
_STATUS = {
    "Finished Airing": "finished_airing",
    "Currently Airing": "currently_airing",
    "Not yet aired": "not_yet_aired",
}
_RATING = {"G": "g", "PG": "pg", "PG-13": "pg_13", "R": "r", "R+": "r+", "Rx": "rx"}
_SEASON_YEAR = re.compile(r"(\d{4})")


class JikanError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(get_settings().jikan_url)


def _snake(value: str | None) -> str | None:
    return re.sub(r"[\s-]+", "_", value.strip().lower()) if value else None


def _duration_s(value: str | None) -> int | None:
    """ "24 min per ep" / "1 hr 55 min" -> seconds."""
    if not value:
        return None
    hours = re.search(r"(\d+)\s*hr", value)
    minutes = re.search(r"(\d+)\s*min", value)
    seconds = re.search(r"(\d+)\s*sec", value)
    total = sum(
        int(m.group(1)) * factor
        for m, factor in ((hours, 3600), (minutes, 60), (seconds, 1))
        if m is not None
    )
    return total or None


def anime_row(item: dict[str, Any]) -> dict[str, Any]:
    """Map a Jikan anime onto the columns of models.Anime (as mal.anime_from_node does)."""
    tags = [
        tag
        for group in ("genres", "explicit_genres", "themes", "demographics")
        for tag in item.get(group) or []
    ]
    images = (item.get("images") or {}).get("jpg") or {}
    year = item.get("year")
    if year is None:
        start = ((item.get("aired") or {}).get("from")) or ""
        found = _SEASON_YEAR.match(start)
        year = int(found.group(1)) if found else None
    season = item.get("season")
    rating = (item.get("rating") or "").split(" - ")[0].strip()
    return {
        "id": item["mal_id"],
        "title": item.get("title") or "",
        "title_en": item.get("title_english") or None,
        "synopsis": item.get("synopsis"),
        "picture_url": images.get("large_image_url") or images.get("image_url"),
        "media_type": _snake(item.get("type")),
        "status": _STATUS.get(item.get("status") or "", _snake(item.get("status"))),
        "num_episodes": item.get("episodes") or None,
        "mean": item.get("score"),
        "popularity": item.get("popularity"),
        "genres": [t["name"] for t in tags],
        "start_season": f"{season} {year}" if season and year else None,
        "genre_tags": [{"id": t["mal_id"], "name": t["name"]} for t in tags],
        "studios": [s["name"] for s in item.get("studios") or []],
        "source": _snake(item.get("source")),
        "rating": _RATING.get(rating),
        "num_list_users": item.get("members"),
        "num_scoring_users": item.get("scored_by"),
        "rank": item.get("rank"),
        "average_episode_duration": _duration_s(item.get("duration")),
        "start_year": year,
        "alt_titles": [
            t
            for t in [
                item.get("title_english"),
                item.get("title_japanese"),
                *(item.get("title_synonyms") or []),
            ]
            if t and t != item.get("title")
        ],
    }


async def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as http:
        try:
            resp = await http.get(f"{get_settings().jikan_url.rstrip('/')}{path}", params=params)
        except httpx.HTTPError as e:
            raise JikanError(f"Jikan unreachable: {e}") from e
    if resp.status_code >= 400:
        raise JikanError(f"Jikan {resp.status_code} for {path}: {resp.text[:200]}")
    return resp.json()


async def genres() -> list[dict[str, Any]]:
    """[{"id", "name", "count"}] for every MAL anime genre, theme and demographic."""
    data = await _get("/genres/anime")
    return [
        {"id": g["mal_id"], "name": g["name"], "count": g.get("count")}
        for g in data.get("data", [])
    ]


async def by_genre(
    genre_id: int, page: int = 1, order: Order = "score"
) -> tuple[list[dict[str, Any]], bool]:
    """One page of shows with this genre: (rows for models.Anime, whether there's a next page)."""
    order_by, sort = ORDER_BY[order]
    data = await _get(
        "/anime",
        {
            "genres": genre_id,
            "order_by": order_by,
            "sort": sort,
            "page": page,
            "limit": PAGE_SIZE,
        },
    )
    rows = [anime_row(item) for item in data.get("data", [])]
    return rows, bool((data.get("pagination") or {}).get("has_next_page"))
