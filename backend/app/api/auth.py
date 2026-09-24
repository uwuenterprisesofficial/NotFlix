import secrets

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import DB
from app.core.config import get_settings
from app.models import User
from app.services import mal

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    if not get_settings().mal_client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "MAL_CLIENT_ID is not configured")
    state, verifier = secrets.token_urlsafe(24), mal.new_code_verifier()
    request.session["oauth"] = {"state": state, "verifier": verifier}
    return RedirectResponse(mal.authorize_url(state, verifier))


@router.get("/callback")
async def callback(
    request: Request,
    db: DB,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    frontend = get_settings().frontend_url
    pending = request.session.pop("oauth", None)
    state_ok = pending is not None and secrets.compare_digest(pending["state"], state or "")
    if error or not code or not state_ok:
        return RedirectResponse(f"{frontend}/?login=failed")

    tokens = await mal.exchange_code(code, pending["verifier"])
    async with mal.MalClient(tokens.access_token) as client:
        profile = await client.me()

    user = await db.scalar(select(User).where(User.mal_user_id == profile["id"]))
    if user is None:
        user = User(mal_user_id=profile["id"])
        db.add(user)
    user.name = profile["name"]
    user.picture = profile.get("picture")
    user.access_token = tokens.access_token
    user.refresh_token = tokens.refresh_token
    user.token_expires_at = tokens.expires_at
    await db.commit()

    request.session["user_id"] = user.id
    return RedirectResponse(f"{frontend}/?login=ok")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> None:
    request.session.clear()
