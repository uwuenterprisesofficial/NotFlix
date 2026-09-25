"""Sign-in with MyAnimeList and/or AniList.

GET /auth/login?provider=mal|anilist starts one provider's OAuth flow. `then=<other>` chains
the other one afterwards (signing in with both), `link=true` adds the account to the signed-in
user instead of signing in (Settings). An account can belong to one user only: linking one
that another user has moves it over (and removes that user if nothing is left).
"""

import secrets
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.models import User
from app.services import anilist_account, mal, stats_jobs

router = APIRouter(prefix="/auth", tags=["auth"])

Provider = Literal["mal", "anilist"]


def configured(provider: str) -> bool:
    if provider == "mal":
        return bool(get_settings().mal_client_id)
    return anilist_account.configured()


@router.get("/providers")
async def providers() -> dict[str, bool]:
    """Which sign-in providers are set up."""
    return {"mal": configured("mal"), "anilist": configured("anilist")}


@router.get("/login")
async def login(
    request: Request,
    provider: Provider = "mal",
    then: Provider | None = None,
    link: bool = False,
) -> RedirectResponse:
    if not configured(provider):
        name = "MAL_CLIENT_ID" if provider == "mal" else "ANILIST_CLIENT_ID/ANILIST_CLIENT_SECRET"
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{name} is not configured")
    if link and not request.session.get("user_id"):
        link = False  # nothing to link to: a plain sign-in
    state = secrets.token_urlsafe(24)
    pending = {"provider": provider, "state": state, "link": link}
    if then and then != provider and configured(then):
        pending["then"] = then
    if provider == "mal":
        pending["verifier"] = mal.new_code_verifier()
        url = mal.authorize_url(state, pending["verifier"])
    else:
        url = anilist_account.authorize_url(state)
    request.session["oauth"] = pending
    return RedirectResponse(url)


def _pending(request: Request, provider: str, state: str | None) -> dict | None:
    pending = request.session.pop("oauth", None)
    if not pending or pending.get("provider") != provider:
        return None
    return pending if secrets.compare_digest(pending["state"], state or "") else None


async def _owner(db: DB, provider: str, account_id: int) -> User | None:
    column = User.mal_user_id if provider == "mal" else User.anilist_user_id
    return await db.scalar(select(User).where(column == account_id))


def _unlink(user: User, provider: str) -> None:
    if provider == "mal":
        user.mal_user_id = user.mal_name = None
        user.access_token = user.refresh_token = user.token_expires_at = None
    else:
        user.anilist_user_id = user.anilist_name = None
        user.anilist_token = user.anilist_token_expires_at = None


async def _finish(
    request: Request, db: DB, pending: dict, account_id: int, name: str, picture: str | None,
    tokens: dict,
) -> RedirectResponse:  # fmt: skip
    provider = pending["provider"]
    frontend = get_settings().frontend_url
    current = None
    if pending.get("link") and request.session.get("user_id"):
        current = await db.get(User, request.session["user_id"])
    owner = await _owner(db, provider, account_id)

    if current is not None:
        if owner is not None and owner.id != current.id:
            # The account moves to the signed-in user.
            _unlink(owner, provider)
            await db.flush()
            if not (owner.has_mal or owner.has_anilist):
                await db.delete(owner)
        user = current
    else:
        user = owner
        if user is None:
            user = User(name=name, picture=picture)
            db.add(user)

    if provider == "mal":
        user.mal_user_id, user.mal_name = account_id, name
    else:
        user.anilist_user_id, user.anilist_name = account_id, name
    for key, value in tokens.items():
        setattr(user, key, value)
    if not user.picture:
        user.picture = picture
    await db.commit()
    request.session["user_id"] = user.id
    if current is not None:
        # Another list is part of the user now: its statistics need recomputing.
        await stats_jobs.forget(user.id)

    if then := pending.get("then"):
        prefix = get_settings().public_api_prefix
        return RedirectResponse(f"{frontend}{prefix}/auth/login?provider={then}&link=true")
    target = "/settings" if pending.get("link") else "/"
    return RedirectResponse(f"{frontend}{target}?login=ok&account={provider}")


@router.get("/callback")
async def callback(
    request: Request,
    db: DB,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """MyAnimeList's OAuth redirect (the URL registered at MAL, so it keeps its name)."""
    pending = _pending(request, "mal", state)
    if error or not code or pending is None:
        return RedirectResponse(f"{get_settings().frontend_url}/?login=failed")
    tokens = await mal.exchange_code(code, pending["verifier"])
    async with mal.MalClient(tokens.access_token) as client:
        profile = await client.me()
    return await _finish(
        request, db, pending, profile["id"], profile["name"], profile.get("picture"),
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_expires_at": tokens.expires_at,
        },
    )  # fmt: skip


@router.get("/anilist/callback")
async def anilist_callback(
    request: Request,
    db: DB,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    pending = _pending(request, "anilist", state)
    if error or not code or pending is None:
        return RedirectResponse(f"{get_settings().frontend_url}/?login=failed")
    try:
        token = await anilist_account.exchange_code(code)
        async with anilist_account.AniListClient(token.access_token) as client:
            viewer = await client.viewer()
    except anilist_account.AniListError:
        return RedirectResponse(f"{get_settings().frontend_url}/?login=failed")
    avatar = viewer.get("avatar") or {}
    return await _finish(
        request, db, pending, viewer["id"], viewer["name"], avatar.get("large"),
        {"anilist_token": token.access_token, "anilist_token_expires_at": token.expires_at},
    )  # fmt: skip


@router.delete("/accounts/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink(provider: Provider, user: CurrentUser, db: DB) -> None:
    """Remove a linked list. The last one can't be removed (sign out instead)."""
    other = user.has_anilist if provider == "mal" else user.has_mal
    if not other:
        raise HTTPException(status.HTTP_409_CONFLICT, "This is your only linked list")
    _unlink(user, provider)
    await db.commit()
    await stats_jobs.forget(user.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> None:
    request.session.clear()
