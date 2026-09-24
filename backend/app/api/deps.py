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


OptionalUser = Annotated[User | None, Depends(current_user_optional)]
CurrentUser = Annotated[User, Depends(current_user)]
