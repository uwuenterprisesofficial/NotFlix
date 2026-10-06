"""Requests that reach the backend with the web app's /api prefix (e.g. a MyAnimeList or AniList
redirect URL registered as https://example.com/api/auth/callback, or a client set up with the
web app's address while the backend is published directly) are served as without it."""

from starlette.types import ASGIApp, Receive, Scope, Send

PREFIX = "/api"


class StripApiPrefix:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path: str = scope["path"]
            if path == PREFIX or path.startswith(f"{PREFIX}/"):
                scope = {**scope, "path": path[len(PREFIX) :] or "/"}
                raw = scope.get("raw_path")
                if raw is not None and raw.startswith(PREFIX.encode()):
                    scope["raw_path"] = raw[len(PREFIX) :] or b"/"
        await self.app(scope, receive, send)
