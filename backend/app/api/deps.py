from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import User

DB = Annotated[AsyncSession, Depends(get_db)]


async def current_user_optional(request: Request, db: DB) -> User | None:
    user_id = request.session.get("user_id")
    return await db.get(User, user_id) if user_id else None


async def current_user(user: Annotated[User | None, Depends(current_user_optional)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in with MyAnimeList first")
    return user


async def list_user(user: Annotated[User, Depends(current_user)]) -> User:
    """A user with a list: guests (Watch Together only) have none."""
    if user.is_guest:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Guests have no list: sign in with one")
    return user


async def signed_in_here(
    user: Annotated[User | None, Depends(current_user_optional)],
) -> User | None:
    """A signed-in user; in hybrid mode (an upstream server, see services/library.py) users sign
    in there, and this server only answers the desktop app it runs in, so anyone may."""
    from app.core.config import get_settings

    if user is None and not get_settings().upstream_url:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in with MyAnimeList first")
    return user


OptionalUser = Annotated[User | None, Depends(current_user_optional)]
# Stream lookups (refreshing, mappings): see signed_in_here.
SignedInHere = Annotated[User | None, Depends(signed_in_here)]
CurrentUser = Annotated[User, Depends(current_user)]
# Anything about the user's own list (progress, statuses, sync, statistics).
ListUser = Annotated[User, Depends(list_user)]
