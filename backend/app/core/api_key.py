"""The API key every request needs (header X-API-Key, compared with API_KEY).

The frontend's server adds it to the requests it passes on (the browser never sees it), so the
API answers nobody else. Only MyAnimeList's and AniList's OAuth redirects come without it: the
browser is sent there by the provider. They only complete a sign-in that was started with the
key (by its one-time `state`), so they need none.
"""

import secrets

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

HEADER = "x-api-key"
MIN_LENGTH = 16
OPEN_PATHS = frozenset({"/auth/callback", "/auth/anilist/callback"})


def check_configured(key: str) -> None:
    if len(key) < MIN_LENGTH:
        got = (
            "it isn't set in this container (check that it reaches it: the environment of the "
            "backend service, or a .env file next to docker-compose.yml)"
            if not key
            else f"it has {len(key)}"
        )
        raise RuntimeError(
            f"API_KEY must be set to at least {MIN_LENGTH} characters, but {got}. Generate one "
            'with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )


class ApiKeyMiddleware:
    """A plain ASGI middleware, so streamed responses (video, event streams) pass untouched."""

    def __init__(self, app: ASGIApp, key: str) -> None:
        self.app = app
        self.key = key.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and scope["path"] not in OPEN_PATHS:
            given = Headers(scope=scope).get(HEADER, "").encode()
            if not secrets.compare_digest(given, self.key):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                response = JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
