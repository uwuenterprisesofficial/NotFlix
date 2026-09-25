"""Thin async client for the official MyAnimeList API v2 (https://myanimelist.net/apiconfig/references/api/v2)."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core import http as shared_http
from app.core.config import get_settings

API_BASE = "https://api.myanimelist.net/v2"
AUTH_BASE = "https://myanimelist.net/v1/oauth2"
ANIME_FIELDS = (
    "id,title,alternative_titles,main_picture,synopsis,mean,popularity,media_type,"
    "status,num_episodes,genres,start_season,start_date,studios,source,rating,num_list_users,"
    "num_scoring_users,rank,average_episode_duration"
)


class MalError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status  # None: MAL wasn't reached

    @property
    def outage(self) -> bool:
        """MAL is down or limiting (not: this request was wrong)."""
        return self.status is None or self.status == 429 or self.status >= 500


def new_code_verifier() -> str:
    return secrets.token_urlsafe(96)[:128]


def authorize_url(state: str, code_verifier: str) -> str:
    s = get_settings()
    # MAL only supports the "plain" PKCE method: the challenge is the verifier itself.
    query = urlencode(
        {
            "response_type": "code",
            "client_id": s.mal_client_id,
            "state": state,
            "redirect_uri": s.mal_redirect_uri,
            "code_challenge": code_verifier,
            "code_challenge_method": "plain",
        }
    )
    return f"{AUTH_BASE}/authorize?{query}"


def _alt_titles(node: dict[str, Any]) -> list[str]:
    alt = node.get("alternative_titles") or {}
    titles = [*(alt.get("synonyms") or []), alt.get("en"), alt.get("ja")]
    return list(dict.fromkeys(t for t in titles if t and t != node.get("title")))


def anime_from_node(node: dict[str, Any]) -> dict[str, Any]:
    """Map a MAL anime node onto the columns of models.Anime."""
    picture = node.get("main_picture") or {}
    season = node.get("start_season")
    return {
        "id": node["id"],
        "title": node["title"],
        "title_en": (node.get("alternative_titles") or {}).get("en") or None,
        "synopsis": node.get("synopsis"),
        "picture_url": picture.get("large") or picture.get("medium"),
        "media_type": node.get("media_type"),
        "status": node.get("status"),
        "num_episodes": node.get("num_episodes") or None,
        "mean": node.get("mean"),
        "popularity": node.get("popularity"),
        "genres": [g["name"] for g in node.get("genres") or []],
        "start_season": f"{season['season']} {season['year']}" if season else None,
        "genre_tags": [{"id": g["id"], "name": g["name"]} for g in node.get("genres") or []],
        "studios": [s["name"] for s in node.get("studios") or []],
        "source": node.get("source"),
        "rating": node.get("rating"),
        "num_list_users": node.get("num_list_users"),
        "num_scoring_users": node.get("num_scoring_users"),
        "rank": node.get("rank"),
        "average_episode_duration": node.get("average_episode_duration") or None,
        "start_year": _year(node.get("start_date"), season),
        "alt_titles": _alt_titles(node),
        "mal_details_at": datetime.now(UTC),
    }


def _year(start_date: str | None, season: dict[str, Any] | None) -> int | None:
    if start_date and start_date[:4].isdigit():
        return int(start_date[:4])
    return season["year"] if season else None


class TokenSet:
    def __init__(self, data: dict[str, Any]):
        self.access_token: str = data["access_token"]
        self.refresh_token: str = data["refresh_token"]
        self.expires_at = datetime.now(UTC) + timedelta(seconds=int(data["expires_in"]))


class MalClient:
    def __init__(self, access_token: str | None = None, http: httpx.AsyncClient | None = None):
        s = get_settings()
        headers = (
            {"Authorization": f"Bearer {access_token}"}
            if access_token
            else {"X-MAL-CLIENT-ID": s.mal_client_id}
        )
        # The shared client, unless one is given (tests).
        self._http = http or shared_http.shared("mal")
        self._headers = headers

    async def __aenter__(self) -> "MalClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass  # the client is shared

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = await self._http.get(url, params=params, headers=self._headers)
        except httpx.HTTPError as e:
            raise MalError(f"MAL unreachable: {e}") from e
        if resp.status_code >= 400:
            raise MalError(f"MAL {resp.status_code} for {url}: {resp.text[:200]}", resp.status_code)
        return resp.json()

    async def me(self) -> dict[str, Any]:
        return await self._get(f"{API_BASE}/users/@me", {"fields": "picture"})

    async def my_animelist(self) -> list[dict[str, Any]]:
        """All entries of the authenticated user's list: [{"node": {...}, "list_status": {...}}]."""
        entries: list[dict[str, Any]] = []
        url: str | None = f"{API_BASE}/users/@me/animelist"
        params: dict[str, Any] | None = {
            "fields": f"list_status,{ANIME_FIELDS}",
            "limit": 1000,
            "nsfw": "true",
        }
        while url:
            page = await self._get(url, params)
            entries.extend(page.get("data", []))
            url, params = (page.get("paging") or {}).get("next"), None
        return entries

    async def anime(self, anime_id: int, extra_fields: str = "") -> dict[str, Any]:
        fields = f"{ANIME_FIELDS},{extra_fields}" if extra_fields else ANIME_FIELDS
        return await self._get(f"{API_BASE}/anime/{anime_id}", {"fields": fields})

    async def ranking(self, ranking_type: str, limit: int = 20) -> list[dict[str, Any]]:
        page = await self._get(
            f"{API_BASE}/anime/ranking",
            {"ranking_type": ranking_type, "limit": limit, "fields": ANIME_FIELDS},
        )
        return [item["node"] for item in page.get("data", [])]

    async def search(self, query: str, limit: int = 30, offset: int = 0) -> list[dict[str, Any]]:
        """MAL's title search (the query needs at least 3 characters)."""
        page = await self._get(
            f"{API_BASE}/anime",
            {"q": query, "limit": limit, "offset": offset, "fields": ANIME_FIELDS, "nsfw": "true"},
        )
        return [item["node"] for item in page.get("data", [])]

    async def update_my_list_status(self, anime_id: int, **fields: Any) -> dict[str, Any]:
        try:
            resp = await self._http.patch(
                f"{API_BASE}/anime/{anime_id}/my_list_status", data=fields, headers=self._headers
            )
        except httpx.HTTPError as e:
            raise MalError(f"MAL unreachable: {e}") from e
        if resp.status_code >= 400:
            raise MalError(f"MAL {resp.status_code}: {resp.text[:200]}", resp.status_code)
        return resp.json()


async def _token_request(data: dict[str, str]) -> TokenSet:
    s = get_settings()
    payload = {"client_id": s.mal_client_id, "client_secret": s.mal_client_secret, **data}
    resp = await shared_http.shared("mal").post(f"{AUTH_BASE}/token", data=payload)
    if resp.status_code >= 400:
        raise MalError(f"MAL token request failed ({resp.status_code}): {resp.text[:200]}")
    return TokenSet(resp.json())


async def exchange_code(code: str, code_verifier: str) -> TokenSet:
    return await _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_settings().mal_redirect_uri,
            "code_verifier": code_verifier,
        }
    )


async def refresh_tokens(refresh_token: str) -> TokenSet:
    return await _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
