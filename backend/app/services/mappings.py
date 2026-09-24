from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import AsyncSessionLocal
from app.models import ProviderMapping


async def get_mapping(anime_id: int, provider: str) -> ProviderMapping | None:
    async with AsyncSessionLocal() as db:
        return await db.scalar(
            select(ProviderMapping).where(
                ProviderMapping.anime_id == anime_id, ProviderMapping.provider == provider
            )
        )


async def save_mapping(
    anime_id: int,
    provider: str,
    external_id: str | None,
    season: int | None = None,
    episode_offset: int = 0,
    manual: bool = False,
) -> None:
    values = {
        "external_id": external_id,
        "season": season,
        "episode_offset": episode_offset,
        "manual": manual,
        "updated_at": datetime.now(UTC),
    }
    stmt = insert(ProviderMapping).values(anime_id=anime_id, provider=provider, **values)
    async with AsyncSessionLocal() as db:
        await db.execute(
            stmt.on_conflict_do_update(index_elements=["anime_id", "provider"], set_=values)
        )
        await db.commit()


async def delete_mapping(anime_id: int, provider: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(ProviderMapping).where(
                ProviderMapping.anime_id == anime_id, ProviderMapping.provider == provider
            )
        )
        await db.commit()
