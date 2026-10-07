"""The user's playlist: shows to play next, in their order. After the last episode there is of
whatever they watch, the first playlist show with an episode to play starts (see
GET /me/up-next).

- Shows added by hand stay until they're finished (completed on the list, or every episode
  watched). An airing show they've caught up with stays too, and plays again once its next
  episode is out.
- With automatic airing shows on, shows on the list as Watching that are airing and have
  episodes the user hasn't watched yet are taken in by themselves, at the end. They leave
  again once caught up, and come back with the next episode.
- Removing an airing show hides it until its next episode (so the automatic ones don't
  come straight back).

The playlist is brought up to date whenever it's read (`current`); airing shows it looks at are
checked with AniList in the background when what's known may be out of date.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Anime, ListEntry, ListStatus, PlaylistItem, User
from app.services import airing

AUTO_STATUSES = {ListStatus.watching}


@dataclass
class Entry:
    item: PlaylistItem
    anime: Anime
    entry: ListEntry | None
    episode: int | None  # the episode to play; None: none aired that hasn't been watched


def aired_now(anime: Anime, now: datetime | None = None) -> int | None:
    """Episodes aired so far as far as known, without asking anyone; None: not known (no
    limit is applied)."""
    now = now or datetime.now(UTC)
    if anime.status == "not_yet_aired":
        return 0
    if anime.status == "finished_airing" or anime.next_episode is None:
        return anime.num_episodes or None
    if anime.next_episode_at is not None and anime.next_episode_at <= now:
        return anime.next_episode
    return anime.next_episode - 1


def next_to_play(anime: Anime, entry: ListEntry | None, now: datetime | None = None) -> int | None:
    """The episode after the ones watched, when it has aired."""
    if anime.status == "not_yet_aired":
        return None
    episode = (entry.episodes_watched if entry else 0) + 1
    if anime.num_episodes and episode > anime.num_episodes:
        return None
    aired = aired_now(anime, now)
    return None if aired is not None and episode > aired else episode


def finished(anime: Anime, entry: ListEntry | None) -> bool:
    if entry is None:
        return False
    if entry.status == ListStatus.completed:
        return True
    return bool(anime.num_episodes) and entry.episodes_watched >= anime.num_episodes


async def _next_position(db: AsyncSession, user_id: int) -> int:
    top = await db.scalar(
        select(func.max(PlaylistItem.position)).where(PlaylistItem.user_id == user_id)
    )
    return (top or 0) + 1


async def current(db: AsyncSession, user: User) -> list[Entry]:
    """The playlist in its order, brought up to date: finished shows leave, automatic ones the
    user caught up with leave, hidden ones whose next episode is out come back, and (when on)
    airing shows with new episodes are taken in. Hidden ones aren't listed."""
    now = datetime.now(UTC)
    entries = {
        e.anime_id: e
        for e in await db.scalars(select(ListEntry).where(ListEntry.user_id == user.id))
    }
    rows = (
        await db.execute(
            select(PlaylistItem, Anime)
            .join(Anime, Anime.id == PlaylistItem.anime_id)
            .where(PlaylistItem.user_id == user.id)
            .order_by(PlaylistItem.position, PlaylistItem.id)
        )
    ).all()
    on_playlist = {item.anime_id for item, _ in rows}
    position = max((item.position for item, _ in rows), default=0) + 1
    out: list[Entry] = []
    changed = False
    for item, anime in rows:
        entry = entries.get(anime.id)
        episode = next_to_play(anime, entry, now)
        if anime.status != "finished_airing":
            airing.check_soon(anime)
        if finished(anime, entry):
            await db.delete(item)
            changed = True
            continue
        if item.hidden_through is not None:
            aired = aired_now(anime, now)
            back = aired is not None and aired > item.hidden_through and episode is not None
            if not (back and (user.playlist_auto_airing or not item.auto)):
                continue
            item.hidden_through = None
            item.position = position
            position += 1
            changed = True
        if item.auto and episode is None:
            await db.delete(item)
            changed = True
            continue
        out.append(Entry(item, anime, entry, episode))

    if user.playlist_auto_airing:
        candidates = (
            await db.execute(
                select(ListEntry, Anime)
                .join(Anime, Anime.id == ListEntry.anime_id)
                .where(
                    ListEntry.user_id == user.id,
                    ListEntry.status.in_(AUTO_STATUSES),
                    Anime.status == "currently_airing",
                )
                .order_by(ListEntry.updated_at.desc().nulls_last())
            )
        ).all()
        for entry, anime in candidates:
            airing.check_soon(anime)
            if anime.id in on_playlist or (episode := next_to_play(anime, entry, now)) is None:
                continue
            if anime.next_episode is None:
                continue  # how far it has aired isn't known
            item = PlaylistItem(user_id=user.id, anime_id=anime.id, position=position, auto=True)
            position += 1
            db.add(item)
            out.append(Entry(item, anime, entry, episode))
            changed = True
    if changed:
        await db.commit()
    out.sort(key=lambda e: e.item.position)
    return out


async def add(db: AsyncSession, user: User, anime_id: int) -> None:
    """Add a show at the end (a hidden or automatic one is kept as added by hand)."""
    item = await db.scalar(
        select(PlaylistItem).where(
            PlaylistItem.user_id == user.id, PlaylistItem.anime_id == anime_id
        )
    )
    if item is None:
        position = await _next_position(db, user.id)
        db.add(PlaylistItem(user_id=user.id, anime_id=anime_id, position=position))
    else:
        if item.hidden_through is not None:
            item.position = await _next_position(db, user.id)
        item.hidden_through = None
        item.auto = False
    await db.commit()


async def remove(db: AsyncSession, user: User, anime_id: int) -> None:
    """Take a show off. An airing one is hidden until its next episode instead (when it would
    be taken in again by itself)."""
    item = await db.scalar(
        select(PlaylistItem).where(
            PlaylistItem.user_id == user.id, PlaylistItem.anime_id == anime_id
        )
    )
    if item is None:
        return
    anime = await db.get(Anime, anime_id)
    entry = await db.scalar(
        select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id == anime_id)
    )
    aired = aired_now(anime) if anime is not None else None
    if anime is not None and anime.status == "currently_airing" and aired is not None:
        item.hidden_through = max(aired, entry.episodes_watched if entry else 0)
        item.auto = True  # (it only comes back with automatic airing shows on)
    else:
        await db.delete(item)
    await db.commit()


async def reorder(db: AsyncSession, user: User, anime_ids: list[int]) -> None:
    """Put the shows in this order; ones not named keep their order after them."""
    items = list(
        await db.scalars(
            select(PlaylistItem)
            .where(PlaylistItem.user_id == user.id)
            .order_by(PlaylistItem.position, PlaylistItem.id)
        )
    )
    rank = {anime_id: i for i, anime_id in enumerate(anime_ids)}
    items.sort(key=lambda i: (i.anime_id not in rank, rank.get(i.anime_id, 0)))
    for position, item in enumerate(items, start=1):
        item.position = position
    await db.commit()
