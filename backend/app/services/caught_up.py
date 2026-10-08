"""Whether the user has watched every episode of a show that's out ("caught up"): such shows
are greyed out in the lists and come after the others in rows like Continue Watching.

How far a show has aired comes from what's known about its next episode, and from the
release calendar (the latest episode it saw air), whichever is further."""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ListStatus
from app.schemas import AnimeCard
from app.services import airing, catalog

CardT = TypeVar("CardT", bound=AnimeCard)

# Shows the user has started (or finished); plan to watch and dropped ones aren't caught up.
STARTED = {ListStatus.watching, ListStatus.on_hold, ListStatus.completed}


async def aired(db: AsyncSession, ids: list[int]) -> dict[int, int | None]:
    """Episodes aired so far per show (None: not known)."""
    now = datetime.now(UTC)
    shows = await catalog.anime_by_ids(db, ids)
    calendar = await airing.latest_aired(db, ids)
    out: dict[int, int | None] = {}
    for anime in shows:
        known = airing.known_aired(anime, now)
        seen = calendar.get(anime.id)
        if anime.status == "finished_airing" or seen is None:
            out[anime.id] = known
        else:
            out[anime.id] = max(known or 0, seen)
    return out


def _caught_up(card: AnimeCard, aired_so_far: int | None) -> bool:
    progress = card.progress
    if progress is None or progress.status not in STARTED:
        return False
    if progress.status == ListStatus.completed:
        return True
    if card.airing is not None:  # New Episodes / calendar: that episode
        return progress.episodes_watched >= card.airing.episode
    if not aired_so_far:
        return False
    return progress.episodes_watched >= aired_so_far


async def mark(db: AsyncSession, cards: Iterable[AnimeCard]) -> None:
    """Set `caught_up` on the cards (the ones with the user's progress)."""
    started = [c for c in cards if c.progress is not None and c.progress.status in STARTED]
    if not started:
        return
    so_far = await aired(db, list({c.id for c in started}))
    for card in started:
        card.caught_up = _caught_up(card, so_far.get(card.id))


def last(cards: Sequence[CardT]) -> list[CardT]:
    """Caught-up shows after the others (otherwise in the same order)."""
    return sorted(cards, key=lambda c: c.caught_up)


async def mark_rows(db: AsyncSession, rows: Iterable, sort: bool = True) -> None:
    """Mark every row's cards, and (with `sort`) put caught-up ones last in each row."""
    rows = list(rows)
    await mark(db, [c for row in rows for c in row.items])
    if sort:
        for row in rows:
            row.items = last(row.items)
