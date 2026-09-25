"""Writing a show's list status to every list the user has linked (MyAnimeList, AniList),
and to the local copy of the list."""

import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ListEntry, User
from app.services import anilist, anilist_account, mal
from app.services.sync_tokens import mal_token

log = logging.getLogger(__name__)


class NotSaved(RuntimeError):
    """No linked list took the change."""


@dataclass
class Saved:
    entry: ListEntry
    failed: list[str] = field(default_factory=list)  # linked lists that didn't take it


async def save(
    db: AsyncSession, user: User, anime_id: int, status: str, episodes: int | None = None
) -> Saved:
    """Set the status (and, when given, the watched episodes) everywhere. Fails only when no
    linked list could be written; MAL's answer counts when there is one."""

    async def to_mal() -> dict:
        fields: dict = {"status": status}
        if episodes is not None:
            fields["num_watched_episodes"] = episodes
        async with mal.MalClient(await mal_token(db, user)) as client:
            return await client.update_my_list_status(anime_id, **fields)

    async def to_anilist() -> dict:
        media_id = await anilist.anilist_id(anime_id)
        if media_id is None:
            raise anilist_account.AniListError("This show isn't on AniList")
        async with anilist_account.AniListClient(user.anilist_token) as client:
            saved = await client.save_entry(media_id, status, episodes)
        progress = saved.get("progress")
        return {"num_episodes_watched": progress} if progress is not None else {}

    writes = {"mal": to_mal} if user.has_mal else {}
    if user.has_anilist:
        writes["anilist"] = to_anilist
    results = await asyncio.gather(*(w() for w in writes.values()), return_exceptions=True)
    outcome = dict(zip(writes, results, strict=True))
    failed = [name for name, r in outcome.items() if isinstance(r, Exception)]
    for name in failed:
        log.warning("Saving anime %s to %s failed: %s", anime_id, name, outcome[name])
    if writes and len(failed) == len(writes):
        raise NotSaved(str(outcome[failed[0]]))
    result = next((r for r in outcome.values() if not isinstance(r, Exception)), {})

    entry = await db.scalar(
        select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id == anime_id)
    )
    if entry is None:
        entry = ListEntry(user_id=user.id, anime_id=anime_id, episodes_watched=0, score=0)
        db.add(entry)
    entry.status = result.get("status", status)
    if episodes is not None or "num_episodes_watched" in result:
        entry.episodes_watched = result.get("num_episodes_watched", episodes)
    entry.score = result.get("score", entry.score or 0)
    await db.commit()
    return Saved(entry, failed)
