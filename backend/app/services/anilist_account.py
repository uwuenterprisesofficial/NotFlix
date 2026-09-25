"""A user's AniList account: OAuth sign-in, reading their anime list and writing to it.

AniList ids differ from MyAnimeList's; NotFlix keys everything by MAL id (AniList's `idMal`),
so list entries without one are skipped.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.models import ListStatus
from app.services.tags import tags_from_names

API_URL = "https://graphql.anilist.co"
AUTH_URL = "https://anilist.co/api/v2/oauth/authorize"
TOKEN_URL = "https://anilist.co/api/v2/oauth/token"
ID_BATCH = 50  # media per request when mapping MAL ids to AniList ids
MAX_RATE_LIMIT_WAIT_S = 90

log = logging.getLogger(__name__)

# AniList list status <-> MAL list status. Rewatching counts as watching.
TO_MAL = {
    "CURRENT": ListStatus.watching,
    "REPEATING": ListStatus.watching,
    "COMPLETED": ListStatus.completed,
    "PAUSED": ListStatus.on_hold,
    "DROPPED": ListStatus.dropped,
    "PLANNING": ListStatus.plan_to_watch,
}
FROM_MAL = {
    ListStatus.watching: "CURRENT",
    ListStatus.completed: "COMPLETED",
    ListStatus.on_hold: "PAUSED",
    ListStatus.dropped: "DROPPED",
    ListStatus.plan_to_watch: "PLANNING",
}
_FORMATS = {
    "TV": "tv", "TV_SHORT": "tv", "MOVIE": "movie", "SPECIAL": "special", "OVA": "ova",
    "ONA": "ona", "MUSIC": "music",
}  # fmt: skip
_STATUSES = {
    "FINISHED": "finished_airing",
    "RELEASING": "currently_airing",
    "NOT_YET_RELEASED": "not_yet_aired",
}


class AniListError(RuntimeError):
    pass


def configured() -> bool:
    s = get_settings()
    return bool(s.anilist_client_id and s.anilist_client_secret)


def authorize_url(state: str) -> str:
    s = get_settings()
    query = urlencode(
        {
            "client_id": s.anilist_client_id,
            "redirect_uri": s.anilist_redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )
    return f"{AUTH_URL}?{query}"


@dataclass(frozen=True)
class Token:
    access_token: str
    expires_at: datetime


async def exchange_code(code: str, http: httpx.AsyncClient | None = None) -> Token:
    s = get_settings()
    payload = {
        "grant_type": "authorization_code",
        "client_id": s.anilist_client_id,
        "client_secret": s.anilist_client_secret,
        "redirect_uri": s.anilist_redirect_uri,
        "code": code,
    }
    client = http or httpx.AsyncClient(timeout=20)
    try:
        resp = await client.post(TOKEN_URL, json=payload, headers={"Accept": "application/json"})
    finally:
        if http is None:
            await client.aclose()
    if resp.status_code >= 400:
        raise AniListError(f"AniList token request failed ({resp.status_code}): {resp.text[:200]}")
    data = resp.json()
    expires_in = int(data.get("expires_in") or 365 * 24 * 3600)
    return Token(data["access_token"], datetime.now(UTC) + timedelta(seconds=expires_in))


class AniListClient:
    """GraphQL calls as the signed-in user (or anonymously, without a token)."""

    def __init__(self, token: str | None = None, http: httpx.AsyncClient | None = None):
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10))
        self._own_http = http is None
        self._headers = {"Accept": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    async def __aenter__(self) -> "AniListClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._own_http:
            await self._http.aclose()

    async def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a query, waiting out AniList's rate limit (HTTP 429 with Retry-After)."""
        waited = 0.0
        while True:
            try:
                resp = await self._http.post(
                    API_URL,
                    json={"query": query, "variables": variables or {}},
                    headers=self._headers,
                )
            except httpx.HTTPError as e:
                raise AniListError(f"AniList unreachable: {e}") from e
            if resp.status_code == 429 and waited < MAX_RATE_LIMIT_WAIT_S:
                delay = float(resp.headers.get("Retry-After") or 30)
                log.info("AniList rate limit; waiting %ss", delay)
                await asyncio.sleep(delay)
                waited += delay
                continue
            body = resp.json() if "json" in resp.headers.get("content-type", "") else {}
            if resp.status_code >= 400 or body.get("errors"):
                message = (body.get("errors") or [{}])[0].get("message") or resp.text[:200]
                raise AniListError(f"AniList {resp.status_code}: {message}")
            return body.get("data") or {}

    async def viewer(self) -> dict[str, Any]:
        data = await self.query("query { Viewer { id name avatar { large medium } } }")
        return data["Viewer"]

    async def animelist(self, user_id: int) -> list[dict[str, Any]]:
        """Every entry of the user's anime list (custom lists merged), as returned."""
        data = await self.query(LIST_QUERY, {"userId": user_id})
        seen: dict[int, dict[str, Any]] = {}
        for group in (data.get("MediaListCollection") or {}).get("lists") or []:
            for entry in group.get("entries") or []:
                seen.setdefault(entry["media"]["id"], entry)
        return list(seen.values())

    async def ids_for(self, mal_ids: list[int]) -> dict[int, int]:
        """MAL id -> AniList media id, for those AniList has."""
        found: dict[int, int] = {}
        for start in range(0, len(mal_ids), ID_BATCH):
            chunk = mal_ids[start : start + ID_BATCH]
            data = await self.query(IDS_QUERY, {"ids": chunk})
            for media in (data.get("Page") or {}).get("media") or []:
                if media.get("idMal"):
                    found[media["idMal"]] = media["id"]
        return found

    async def save_entry(
        self,
        media_id: int,
        status: str,
        progress: int | None = None,
        score: int | None = None,
    ) -> dict[str, Any]:
        """Create or update a list entry. `status` is a MAL list status; `score` is 1-10."""
        variables: dict[str, Any] = {"mediaId": media_id, "status": FROM_MAL[ListStatus(status)]}
        if progress is not None:
            variables["progress"] = progress
        if score:
            variables["scoreRaw"] = score * 10  # 0-100, whatever format the user displays
        data = await self.query(SAVE_MUTATION, variables)
        return data["SaveMediaListEntry"]


_MEDIA = """
id idMal episodes format status averageScore popularity duration source
title { romaji english native } synonyms coverImage { extraLarge large } description(asHtml: false)
genres season seasonYear startDate { year } studios(isMain: true) { nodes { name } }
"""

LIST_QUERY = f"""
query ($userId: Int) {{
  MediaListCollection(userId: $userId, type: ANIME) {{
    lists {{ entries {{
      status progress updatedAt score(format: POINT_10)
      media {{ {_MEDIA} }}
    }} }}
  }}
}}
"""

IDS_QUERY = """
query ($ids: [Int]) {
  Page(perPage: 50) { media(idMal_in: $ids, type: ANIME) { id idMal } }
}
"""

SAVE_MUTATION = """
mutation ($mediaId: Int, $status: MediaListStatus, $progress: Int, $scoreRaw: Int) {
  SaveMediaListEntry(mediaId: $mediaId, status: $status, progress: $progress, scoreRaw: $scoreRaw) {
    id status progress score(format: POINT_10)
  }
}
"""


def anime_row(media: dict[str, Any]) -> dict[str, Any]:
    """AniList media onto models.Anime's columns, for shows MAL's own data isn't there for yet.
    MAL's members count is left empty, so its details are fetched from MAL later."""
    title = media.get("title") or {}
    cover = media.get("coverImage") or {}
    season, year = media.get("season"), media.get("seasonYear")
    genres = media.get("genres") or []
    score = media.get("averageScore")
    return {
        "id": media["idMal"],
        "title": title.get("romaji") or title.get("english") or "",
        "title_en": title.get("english") or None,
        "synopsis": media.get("description"),
        "picture_url": cover.get("extraLarge") or cover.get("large"),
        "media_type": _FORMATS.get(media.get("format") or ""),
        "status": _STATUSES.get(media.get("status") or ""),
        "num_episodes": media.get("episodes"),
        "mean": round(score / 10, 2) if score else None,
        "genres": genres,
        "start_season": f"{season.lower()} {year}" if season and year else None,
        "genre_tags": tags_from_names(genres),
        "studios": [s["name"] for s in (media.get("studios") or {}).get("nodes") or []],
        "source": (media.get("source") or "").lower() or None,
        "average_episode_duration": (media.get("duration") or 0) * 60 or None,
        "start_year": (media.get("startDate") or {}).get("year") or year,
        "alt_titles": [
            t
            for t in [title.get("english"), title.get("native"), *(media.get("synonyms") or [])]
            if t and t != title.get("romaji")
        ],
    }


@dataclass(frozen=True)
class AniListEntry:
    mal_id: int
    media_id: int
    status: str  # MAL list status
    score: int  # 0-10, 0 = unscored
    episodes_watched: int
    updated_at: datetime | None
    media: dict[str, Any]


def parse_entries(raw: list[dict[str, Any]]) -> tuple[list[AniListEntry], int]:
    """List entries with a MAL id, and how many were skipped for lacking one."""
    entries, skipped = [], 0
    for e in raw:
        media = e.get("media") or {}
        if not media.get("idMal") or e.get("status") not in TO_MAL:
            skipped += 1
            continue
        updated = e.get("updatedAt")
        entries.append(
            AniListEntry(
                mal_id=media["idMal"],
                media_id=media["id"],
                status=TO_MAL[e["status"]].value,
                score=round(e.get("score") or 0),
                episodes_watched=e.get("progress") or 0,
                updated_at=datetime.fromtimestamp(updated, UTC) if updated else None,
                media=media,
            )
        )
    return entries, skipped
