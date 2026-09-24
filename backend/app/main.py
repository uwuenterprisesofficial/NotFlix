from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api import anime, auth, browse, me
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="NotFlix API", version="0.1.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="notflix_session",
    max_age=60 * 60 * 24 * 30,
    same_site="lax",
    https_only=settings.frontend_url.startswith("https://"),
)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(browse.router)
app.include_router(anime.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
