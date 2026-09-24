"""MyAnimeList id -> AniList id, titles and season number (via AniList's public GraphQL API)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.services.mappings import get_mapping, save_mapping

API_URL = "https://graphql.anilist.co"
SEASON_FORMATS = {"TV", "TV_SHORT", "ONA"}
PREQUEL_DEPTH = 6
RETRY_NOT_FOUND_AFTER = timedelta(days=1)

_NODE = "id type format title { romaji english } synonyms"


def _relations(depth: int) -> str:
    if depth == 0:
        return ""
    return f"relations {{ edges {{ relationType node {{ {_NODE} {_relations(depth - 1)} }} }} }}"


QUERY = f"""
query ($mal: Int) {{
  Media(idMal: $mal, type: ANIME) {{ {_NODE} {_relations(PREQUEL_DEPTH)} }}
}}
"""


@dataclass(frozen=True)
class AniListInfo:
    id: int
    season: int  # 1 + number of earlier TV seasons in the prequel chain
    titles: list[str]
    root_titles: list[str]  # titles of the first season, which streaming sites name series after


def _titles(media: dict[str, Any]) -> list[str]:
    title = media.get("title") or {}
    found = [title.get("english"), title.get("romaji"), *(media.get("synonyms") or [])]
    return [t for t in found if t]


def parse_media(media: dict[str, Any]) -> AniListInfo:
    prequels: list[dict[str, Any]] = []
    node = media
    while True:
        edges = (node.get("relations") or {}).get("edges") or []
        prequel = next(
            (
                e["node"]
                for e in edges
                if e.get("relationType") == "PREQUEL" and e["node"].get("type") == "ANIME"
            ),
            None,
        )
        if prequel is None:
            break
        prequels.append(prequel)
        node = prequel

    seasons = [p for p in prequels if p.get("format") in SEASON_FORMATS]
    root = seasons[-1] if seasons else media
    return AniListInfo(
        id=media["id"],
        season=len(seasons) + 1 if media.get("format") in SEASON_FORMATS else 1,
        titles=_titles(media),
        root_titles=_titles(root),
    )


async def lookup(mal_id: int, http: httpx.AsyncClient | None = None) -> AniListInfo | None:
    client = http or httpx.AsyncClient(timeout=15)
    try:
        resp = await client.post(API_URL, json={"query": QUERY, "variables": {"mal": mal_id}})
    finally:
        if http is None:
            await client.aclose()
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    media = (resp.json().get("data") or {}).get("Media")
    return parse_media(media) if media else None


async def anilist_id(mal_id: int) -> int | None:
    """Cached MAL -> AniList id mapping."""
    mapping = await get_mapping(mal_id, "anilist")
    if mapping is not None and mapping.external_id:
        return int(mapping.external_id)
    if mapping is not None and datetime.now(UTC) - mapping.updated_at < RETRY_NOT_FOUND_AFTER:
        return None
    info = await lookup(mal_id)
    await save_mapping(
        mal_id, "anilist", str(info.id) if info else None, info.season if info else None
    )
    return info.id if info else None
