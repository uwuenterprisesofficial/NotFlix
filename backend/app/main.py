from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api import (
    admin,
    anime,
    auth,
    browse,
    calendar,
    friends,
    library,
    me,
    playlist,
    proxy,
    search,
    streams,
    together,
)
from app.core.api_key import ApiKeyMiddleware, check_configured
from app.core.config import get_settings
from app.core.prefix import StripApiPrefix

settings = get_settings()
check_configured(settings.api_key)

app = FastAPI(title="NotFlix API", version="0.1.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="notflix_session",
    max_age=60 * 60 * 24 * 30,
    same_site="lax",
    https_only=settings.frontend_url.startswith("https://"),
)
# Added last, so it runs first: without the key nothing else happens (not even a session).
app.add_middleware(ApiKeyMiddleware, key=settings.api_key)
# Outermost: /api/... is served as /... (also the sign-in redirects that need no key).
app.add_middleware(StripApiPrefix)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(playlist.router)
app.include_router(browse.router)
app.include_router(search.router)
app.include_router(calendar.router)
app.include_router(anime.router)
app.include_router(streams.router)
app.include_router(streams.providers_router)
app.include_router(proxy.router)
app.include_router(together.router)
app.include_router(admin.router)
app.include_router(library.router)
app.include_router(friends.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
