from typing import cast

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import StreamSource
from app.providers.base import (
    AnimeInfo,
    Found,
    Language,
    ProviderError,
    Resolved,
    SourceOption,
    Stream,
)

LANGUAGES = {"de-dub", "de-sub", "en-dub", "en-sub"}


def _stream(row: StreamSource) -> Stream:
    if row.kind == "embed":
        return Stream(kind="embed", url=row.url, label=row.provider)
    is_hls = ".m3u8" in row.url.split("?")[0].lower()
    return Stream(
        kind="direct", url=row.url, label=row.provider, format="hls" if is_hls else "file"
    )


class DatabaseProvider:
    """Sources stored in the stream_sources table (added by hand or by an importer)."""

    name = "database"
    lists_whole_show = True

    async def scan(
        self, anime: AnimeInfo, episodes: list[int], found: Found | None = None
    ) -> dict[int, list[SourceOption]]:
        """Every stored source of the show in one query."""
        async with AsyncSessionLocal() as db:
            rows = await db.scalars(
                select(StreamSource)
                .where(StreamSource.anime_id == anime.id, StreamSource.episode.in_(episodes))
                .order_by(StreamSource.id)
            )
            results: dict[int, list[SourceOption]] = {ep: [] for ep in episodes}
            for row in rows:
                results[row.episode].append(self._option(row))
        return results

    def _option(self, row: StreamSource) -> SourceOption:
        return SourceOption(
            id=f"{self.name}:{row.id}",
            provider=self.name,
            label=row.provider,
            language=cast(Language, row.language) if row.language in LANGUAGES else "unknown",
            resolved=Resolved(streams=[_stream(row)]),
        )

    async def options(self, anime: AnimeInfo, episode: int) -> list[SourceOption]:
        async with AsyncSessionLocal() as db:
            rows = await db.scalars(
                select(StreamSource)
                .where(StreamSource.anime_id == anime.id, StreamSource.episode == episode)
                .order_by(StreamSource.id)
            )
            return [self._option(row) for row in rows]

    async def resolve(self, anime: AnimeInfo, episode: int, key: str) -> Resolved:
        async with AsyncSessionLocal() as db:
            row = await db.get(StreamSource, int(key)) if key.isdigit() else None
        if row is None or row.anime_id != anime.id or row.episode != episode:
            raise ProviderError("Source not found")
        return Resolved(streams=[_stream(row)])
