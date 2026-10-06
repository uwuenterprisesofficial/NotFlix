"""Recommending a show to a friend (someone the user is connected with, see together.py), with
an optional note. The friend finds it on their home page and their My List page; the sender sees
where the friend is with it. Only shows between current friends are listed: disconnecting
hides them."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser
from app.models import Anime, Connection, FriendRecommendation, ListEntry, ListStatus, User
from app.schemas import (
    FriendForShowOut,
    FriendRecommendationIn,
    FriendRecommendationOut,
    FriendRecommendationsOut,
    PersonOut,
    Progress,
    ShowRecommendationsOut,
)
from app.services import catalog
from app.services.taste import predictor_for

router = APIRouter(prefix="/friends", tags=["friends"])

LIST_LIMIT = 100
# A friend's recommendation of a show the user finished or dropped isn't offered on the home page.
DONE = {ListStatus.completed, ListStatus.dropped}


def _person(user: User) -> PersonOut:
    return PersonOut(id=user.id, name=user.name, picture=user.picture)


def _progress(entry: ListEntry | None) -> Progress | None:
    if entry is None:
        return None
    return Progress(status=entry.status, episodes_watched=entry.episodes_watched, score=entry.score)


async def friends(db: AsyncSession, user_id: int) -> dict[int, tuple[Connection, User]]:
    """The user's friends by their user id: the connection and the friend."""
    conns = (
        await db.scalars(
            select(Connection)
            .where(or_(Connection.user_a_id == user_id, Connection.user_b_id == user_id))
            .order_by(Connection.created_at)
        )
    ).all()
    ids = [c.partner_of(user_id) for c in conns]
    people = {u.id: u for u in await db.scalars(select(User).where(User.id.in_(ids)))}
    return {
        c.partner_of(user_id): (c, people[c.partner_of(user_id)])
        for c in conns
        if c.partner_of(user_id) in people
    }


async def _entries(
    db: AsyncSession, pairs: set[tuple[int, int]]
) -> dict[tuple[int, int], ListEntry]:
    """List entries by (user id, anime id)."""
    if not pairs:
        return {}
    users = {u for u, _ in pairs}
    shows = {a for _, a in pairs}
    found = await db.scalars(
        select(ListEntry).where(ListEntry.user_id.in_(users), ListEntry.anime_id.in_(shows))
    )
    return {(e.user_id, e.anime_id): e for e in found if (e.user_id, e.anime_id) in pairs}


async def _out(
    db: AsyncSession, user: User, rows: list[FriendRecommendation], people: dict[int, User]
) -> list[FriendRecommendationOut]:
    """Received ones (to the user) show the sender, the user's progress and predicted score;
    sent ones the friend and where they are with the show."""
    shows = {a.id: a for a in await catalog.anime_by_ids(db, list({r.anime_id for r in rows}))}
    theirs = {(r.to_user_id, r.anime_id) for r in rows if r.from_user_id == user.id}
    entries = await _entries(db, theirs | {(user.id, r.anime_id) for r in rows})
    predictor = await predictor_for(db, user)
    out = []
    for r in rows:
        anime = shows.get(r.anime_id)
        sent = r.from_user_id == user.id
        other = people.get(r.to_user_id if sent else r.from_user_id)
        if anime is None or other is None:
            continue
        out.append(
            FriendRecommendationOut(
                id=r.id,
                person=_person(other),
                anime=catalog.to_card(anime, entries.get((user.id, anime.id)), predictor=predictor),
                message=r.message,
                created_at=r.created_at,
                seen=r.seen_at is not None,
                dismissed=r.dismissed,
                their_progress=_progress(entries.get((r.to_user_id, anime.id))) if sent else None,
            )
        )
    return out


def _received(user_id: int, friend_ids: list[int]):
    return select(FriendRecommendation).where(
        FriendRecommendation.to_user_id == user_id,
        FriendRecommendation.from_user_id.in_(friend_ids),
        FriendRecommendation.dismissed.is_(False),
    )


async def unseen(db: AsyncSession, user_id: int) -> int:
    """Recommendations from friends the user hasn't looked at yet (the navigation's badge)."""
    ids = list(await friends(db, user_id))
    query = _received(user_id, ids).where(FriendRecommendation.seen_at.is_(None))
    return await db.scalar(select(func.count()).select_from(query.subquery())) or 0


async def for_home(db: AsyncSession, user: User) -> list[tuple[Anime, str]]:
    """Friends' recommendations for the home page (newest first, one per show), unless the user
    finished or dropped the show: (show, "friend:<name>")."""
    people = await friends(db, user.id)
    rows = (
        await db.scalars(
            _received(user.id, list(people)).order_by(FriendRecommendation.created_at.desc())
        )
    ).all()
    shows = {a.id: a for a in await catalog.anime_by_ids(db, list({r.anime_id for r in rows}))}
    entries = await _entries(db, {(user.id, r.anime_id) for r in rows})
    found: dict[int, tuple[Anime, str]] = {}
    for r in rows:
        entry = entries.get((user.id, r.anime_id))
        if r.anime_id in found or r.anime_id not in shows or (entry and entry.status in DONE):
            continue
        found[r.anime_id] = (shows[r.anime_id], f"friend:{people[r.from_user_id][1].name}")
    return list(found.values())


@router.get("/recommendations", response_model=FriendRecommendationsOut)
async def recommendations(user: CurrentUser, db: DB):
    """What friends recommended to the user, and what the user recommended to them (newest
    first)."""
    people = await friends(db, user.id)
    ids = list(people)
    received = (
        await db.scalars(
            _received(user.id, ids)
            .order_by(FriendRecommendation.created_at.desc())
            .limit(LIST_LIMIT)
        )
    ).all()
    sent = (
        await db.scalars(
            select(FriendRecommendation)
            .where(
                FriendRecommendation.from_user_id == user.id,
                FriendRecommendation.to_user_id.in_(ids),
            )
            .order_by(FriendRecommendation.created_at.desc())
            .limit(LIST_LIMIT)
        )
    ).all()
    by_id = {i: person for i, (_, person) in people.items()}
    return FriendRecommendationsOut(
        received=await _out(db, user, list(received), by_id),
        sent=await _out(db, user, list(sent), by_id),
        unseen=sum(1 for r in received if r.seen_at is None),
    )


@router.post("/recommendations/seen", status_code=status.HTTP_204_NO_CONTENT)
async def mark_seen(user: CurrentUser, db: DB) -> None:
    await db.execute(
        update(FriendRecommendation)
        .where(FriendRecommendation.to_user_id == user.id, FriendRecommendation.seen_at.is_(None))
        .values(seen_at=datetime.now(UTC))
    )
    await db.commit()


@router.get("/recommendations/anime/{anime_id}", response_model=ShowRecommendationsOut)
async def for_show(anime_id: int, user: CurrentUser, db: DB):
    """For a show's page: the user's friends (whether it was recommended to them already, and
    where they are with it), and who recommended it to the user."""
    people = await friends(db, user.id)
    rows = (
        await db.scalars(
            select(FriendRecommendation).where(
                FriendRecommendation.anime_id == anime_id,
                or_(
                    FriendRecommendation.from_user_id == user.id,
                    FriendRecommendation.to_user_id == user.id,
                ),
            )
        )
    ).all()
    sent = {r.to_user_id: r for r in rows if r.from_user_id == user.id}
    received = [
        r for r in rows if r.to_user_id == user.id and r.from_user_id in people and not r.dismissed
    ]
    entries = await _entries(db, {(friend_id, anime_id) for friend_id in people})
    by_id = {i: person for i, (_, person) in people.items()}
    return ShowRecommendationsOut(
        friends=[
            FriendForShowOut(
                connection_id=conn.id,
                person=_person(person),
                recommended_at=sent[friend_id].created_at if friend_id in sent else None,
                their_progress=_progress(entries.get((friend_id, anime_id))),
            )
            for friend_id, (conn, person) in people.items()
        ],
        received=await _out(
            db, user, sorted(received, key=lambda r: r.created_at, reverse=True), by_id
        ),
    )


@router.post("/recommendations", response_model=ShowRecommendationsOut)
async def recommend(body: FriendRecommendationIn, user: CurrentUser, db: DB):
    """Recommend a show to friends (by their connections). Again to the same friend: the note
    is replaced and it counts as new for them."""
    anime = await catalog.get_anime(db, body.anime_id)
    if anime is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
    by_connection = {
        conn.id: friend_id for friend_id, (conn, _) in (await friends(db, user.id)).items()
    }
    unknown = set(body.connection_ids) - set(by_connection)
    if unknown:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such friend")
    message = (body.message or "").strip() or None
    now = datetime.now(UTC)
    for connection_id in dict.fromkeys(body.connection_ids):
        friend_id = by_connection[connection_id]
        existing = await db.scalar(
            select(FriendRecommendation).where(
                FriendRecommendation.from_user_id == user.id,
                FriendRecommendation.to_user_id == friend_id,
                FriendRecommendation.anime_id == anime.id,
            )
        )
        if existing is None:
            db.add(
                FriendRecommendation(
                    from_user_id=user.id,
                    to_user_id=friend_id,
                    anime_id=anime.id,
                    message=message,
                    created_at=now,
                )  # fmt: skip
            )
        else:
            existing.message = message
            existing.created_at = now
            existing.seen_at = None
            existing.dismissed = False
    await db.commit()
    return await for_show(anime.id, user, db)


@router.delete("/recommendations/{recommendation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(recommendation_id: int, user: CurrentUser, db: DB) -> None:
    """The sender takes it back; the friend puts it aside (the sender sees that)."""
    found = await db.get(FriendRecommendation, recommendation_id)
    if found is None or user.id not in (found.from_user_id, found.to_user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recommendation")
    if found.from_user_id == user.id:
        await db.delete(found)
    else:
        found.dismissed = True
        found.seen_at = found.seen_at or datetime.now(UTC)
    await db.commit()
