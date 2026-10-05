"""Sign-in with MyAnimeList and/or AniList.

GET /auth/login?provider=mal|anilist starts one provider's OAuth flow. `then=<other>` chains
the other one afterwards (signing in with both), `link=true` adds the account to the signed-in
user instead of signing in (Settings). An account can belong to one user only: linking one
that another user has moves it over (and removes that user if nothing is left).

A frontend on another origin (the desktop app's local server on http://127.0.0.1:<port>) signs
in through the same flow: the provider sends the browser back to the registered redirect URL
(the server), so the pending login is kept in Redis by its `state`, not in the session cookie.
After the callback, a one-time token carries the sign-in back to that origin
(`/auth/handoff`), which sets the session there. Only loopback origins are accepted, so a
token can never be sent to another site.
"""

import json
import secrets
from typing import Any, Literal
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.cache import redis
from app.core.config import get_settings
from app.models import User
from app.services import anilist_account, mal, stats_jobs, sync_jobs, together

router = APIRouter(prefix="/auth", tags=["auth"])

Provider = Literal["mal", "anilist"]

PENDING_TTL_S = 15 * 60  # time to finish signing in at the provider
HANDOFF_TTL_S = 120
# The header the frontend's proxy sets: the origin the browser talks to.
ORIGIN_HEADER = "x-notflix-origin"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def desktop_origin(value: str | None) -> str | None:
    """A frontend origin other than FRONTEND_URL that sign-ins return to: only loopback ones
    (the desktop app's own server). Anything else is ignored."""
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or parts.hostname not in LOOPBACK_HOSTS:
        return None
    origin = f"{parts.scheme}://{parts.netloc}"
    frontend = urlsplit(get_settings().frontend_url)
    return None if origin == f"{frontend.scheme}://{frontend.netloc}" else origin


def _frontend(pending: dict | None) -> str:
    return (pending or {}).get("origin") or get_settings().frontend_url


def _failed(pending: dict | None, provider: Provider, reason: str) -> RedirectResponse:
    """Back to the sign-in page, saying why: "denied" (not allowed at the provider), "expired"
    (no such sign-in, or too old) or "token" (the provider didn't take the client secret)."""
    query = f"login=failed&provider={provider}&reason={reason}"
    return RedirectResponse(f"{_frontend(pending)}/login?{query}")


def configured(provider: str) -> bool:
    if provider == "mal":
        return bool(get_settings().mal_client_id)
    return anilist_account.configured()


@router.get("/providers")
async def providers() -> dict[str, Any]:
    """Which sign-in providers are set up, the web app's public address (FRONTEND_URL, e.g. for
    invite links made in the desktop app), and the redirect URLs to register at the providers
    (shown when a provider rejects a sign-in)."""
    settings = get_settings()
    return {
        "mal": configured("mal"),
        "anilist": configured("anilist"),
        "public_url": settings.frontend_url,
        "redirects": {"mal": settings.mal_redirect_uri, "anilist": settings.anilist_redirect_uri},
    }


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
    if signed_in := request.session.get("user_id"):
        # Who's signed in (on the origin the login started from): a guest becomes, or merges
        # into, the account.
        pending["session_user"] = signed_in
        if link:
            pending["user_id"] = signed_in
    if then and then != provider and configured(then):
        pending["then"] = then
    # Started from the desktop app (its proxy says so).
    if desktop := desktop_origin(request.headers.get(ORIGIN_HEADER)):
        pending["origin"] = desktop
    if provider == "mal":
        pending["verifier"] = mal.new_code_verifier()
        url = mal.authorize_url(state, pending["verifier"])
    else:
        url = anilist_account.authorize_url(state)
    # By state, not in the session: the callback may arrive on another origin than this.
    await redis().set(f"oauth:{state}", json.dumps(pending), ex=PENDING_TTL_S)
    return RedirectResponse(url)


async def _pending(provider: str, state: str | None) -> dict | None:
    if not state:
        return None
    raw = await redis().getdel(f"oauth:{state}")
    pending = json.loads(raw) if raw else None
    if not pending or pending.get("provider") != provider:
        return None
    return pending if secrets.compare_digest(pending["state"], state) else None


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
    if pending.get("link") and pending.get("user_id"):
        current = await db.get(User, pending["user_id"])
    owner = await _owner(db, provider, account_id)

    # A Watch Together guest signing in keeps their connections: the guest becomes this
    # account's user, or (when the account has one already) merges into it.
    session_user = await db.get(User, pending.get("session_user") or 0)
    guest = session_user if session_user is not None and session_user.is_guest else None
    if guest is not None:
        if owner is None:
            current = guest
        else:
            await together.absorb_guest(db, guest, owner)
            current = None
    upgraded = current is not None and current.is_guest

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
    if upgraded:
        user.is_guest = False
        user.name, user.picture = name, picture
    if not user.picture:
        user.picture = picture
    first_sign_in = user.last_synced_at is None
    await db.commit()
    request.session["user_id"] = user.id
    if current is not None:
        # Another list is part of the user now: its statistics need recomputing.
        await stats_jobs.forget(user.id)
    if first_sign_in or current is not None:
        # The new list in NotFlix right away, without pressing "Sync".
        sync_jobs.start(user.id)

    prefix = get_settings().public_api_prefix
    if then := pending.get("then"):
        # The next provider, linked to this user (the session says who).
        target = f"{prefix}/auth/login?provider={then}&link=true"
    else:
        target = "/settings" if pending.get("link") else "/"
        target = f"{target}?login=ok&account={provider}"
    if origin := pending.get("origin"):
        # Back to the desktop app: a one-time token signs it in there. (Signing in with both,
        # the second sign-in then starts there too, through its proxy, which has the API key.)
        token = secrets.token_urlsafe(32)
        await redis().set(f"handoff:{token}", user.id, ex=HANDOFF_TTL_S)
        return RedirectResponse(
            f"{origin}{prefix}/auth/handoff?token={token}&to={quote(target, safe='')}"
        )
    return RedirectResponse(f"{frontend}{target}")


@router.get("/handoff")
async def handoff(request: Request, token: str, to: str = "/") -> RedirectResponse:
    """Finish a sign-in that took place on another origin (see the module docstring): the
    token (once, for 2 minutes) sets this origin's session."""
    user_id = await redis().getdel(f"handoff:{token}")
    # Relative paths only: the browser stays on the origin it came from.
    if not to.startswith("/") or to.startswith(("//", "/\\")):
        to = "/"
    if user_id is None:
        return RedirectResponse("/login?login=failed&reason=expired")
    request.session["user_id"] = int(user_id)
    return RedirectResponse(to)


@router.get("/callback")
async def callback(
    request: Request,
    db: DB,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """MyAnimeList's OAuth redirect (the URL registered at MAL, so it keeps its name)."""
    pending = await _pending("mal", state)
    if pending is None:
        return _failed(None, "mal", "expired")
    if error or not code:
        return _failed(pending, "mal", "denied")
    try:
        tokens = await mal.exchange_code(code, pending["verifier"])
        async with mal.MalClient(tokens.access_token) as client:
            profile = await client.me()
    except mal.MalError:
        return _failed(pending, "mal", "token")
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
    pending = await _pending("anilist", state)
    if pending is None:
        return _failed(None, "anilist", "expired")
    if error or not code:
        return _failed(pending, "anilist", "denied")
    try:
        token = await anilist_account.exchange_code(code)
        async with anilist_account.AniListClient(token.access_token) as client:
            viewer = await client.viewer()
    except anilist_account.AniListError:
        return _failed(pending, "anilist", "token")
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
