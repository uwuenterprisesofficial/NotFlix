from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services import mal


async def mal_token(db: AsyncSession, user: User) -> str:
    """The user's MyAnimeList access token, refreshed when it's about to expire."""
    if user.token_expires_at - datetime.now(UTC) < timedelta(minutes=5):
        tokens = await mal.refresh_tokens(user.refresh_token)
        user.access_token = tokens.access_token
        user.refresh_token = tokens.refresh_token
        user.token_expires_at = tokens.expires_at
        await db.commit()
    return user.access_token
