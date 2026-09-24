from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StreamSource

SourceKind = Literal["embed", "direct"]


@dataclass(frozen=True)
class Source:
    provider: str
    kind: SourceKind  # "embed" = page shown in an <iframe>, "direct" = mp4/HLS the app plays itself
    url: str


class StreamProvider(Protocol):
    """Implement this to plug a streaming site in; register it in PROVIDERS."""

    name: str

    async def sources(self, db: AsyncSession, anime_id: int, episode: int) -> list[Source]: ...


class DatabaseProvider:
    """Serves sources stored in the stream_sources table (added manually or by importers)."""

    name = "database"

    async def sources(self, db: AsyncSession, anime_id: int, episode: int) -> list[Source]:
        rows = await db.scalars(
            select(StreamSource)
            .where(StreamSource.anime_id == anime_id, StreamSource.episode == episode)
            .order_by(StreamSource.id)
        )
        return [Source(provider=r.provider, kind=r.kind, url=r.url) for r in rows]


PROVIDERS: list[StreamProvider] = [DatabaseProvider()]


async def find_sources(db: AsyncSession, anime_id: int, episode: int) -> list[Source]:
    found: list[Source] = []
    for provider in PROVIDERS:
        found.extend(await provider.sources(db, anime_id, episode))
    # Direct sources first: only those support intro/outro skipping.
    return sorted(found, key=lambda s: s.kind != "direct")
