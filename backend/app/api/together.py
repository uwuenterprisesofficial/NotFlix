"""Watch Together: connect with someone (an invite link), get recommendations for both of you,
and watch with a synced player (a room per connection, followed through server-sent events)."""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select

from app.api.deps import DB, CurrentUser, OptionalUser
from app.db.session import AsyncSessionLocal
from app.models import Anime, Connection, ConnectionInvite, ListEntry, User
from app.schemas import (
    CompatibilityOut,
    ConnectionOut,
    InviteInfo,
    InviteOut,
    PairOut,
    PersonOut,
    RoomOut,
    RoomState,
    RoomUpdate,
    Row,
    TogetherOut,
)
from app.services import catalog, rooms, together
from app.services.taste import predictor_for

router = APIRouter(prefix="/together", tags=["together"])

INVITE_TTL = timedelta(days=7)
ROW_ORDER = ["continue", "together", "planned", "show_to_partner", "show_to_me", "both_loved"]


def _person(user: User) -> PersonOut:
    return PersonOut(id=user.id, name=user.name, picture=user.picture)


async def _connection(db: DB, connection_id: int, user: User) -> tuple[Connection, User]:
    """The user's connection and their partner; 404 for anyone else's."""
    conn = await db.get(Connection, connection_id)
    if conn is None or user.id not in (conn.user_a_id, conn.user_b_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connection")
    partner = await db.get(User, conn.partner_of(user.id))
    if partner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connection")
    return conn, partner


# Invites


@router.post("/invites", response_model=InviteOut)
async def create_invite(user: CurrentUser, db: DB):
    """A link to send someone: whoever opens it (signed in) is connected with you."""
    invite = ConnectionInvite(
        code=secrets.token_urlsafe(12),
        user_id=user.id,
        expires_at=datetime.now(UTC) + INVITE_TTL,
    )
    db.add(invite)
    await db.commit()
    return InviteOut(code=invite.code, expires_at=invite.expires_at)


async def _invite(db: DB, code: str) -> tuple[ConnectionInvite, User]:
    invite = await db.get(ConnectionInvite, code)
    inviter = await db.get(User, invite.user_id) if invite else None
    if invite is None or inviter is None or invite.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invite doesn't exist or expired")
    return invite, inviter


async def _between(db: DB, one: int, other: int) -> Connection | None:
    a, b = sorted((one, other))
    return await db.scalar(
        select(Connection).where(Connection.user_a_id == a, Connection.user_b_id == b)
    )


@router.get("/invites/{code}", response_model=InviteInfo)
async def invite_info(code: str, user: OptionalUser, db: DB):
    invite, inviter = await _invite(db, code)
    existing = await _between(db, user.id, inviter.id) if user else None
    return InviteInfo(
        inviter=_person(inviter),
        expires_at=invite.expires_at,
        own=user is not None and user.id == inviter.id,
        connection_id=existing.id if existing else None,
    )


@router.post("/invites/{code}/accept", response_model=ConnectionOut)
async def accept_invite(code: str, user: CurrentUser, db: DB):
    invite, inviter = await _invite(db, code)
    if inviter.id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "That's your own invite")
    conn = await _between(db, user.id, inviter.id)
    if conn is None:
        a, b = sorted((user.id, inviter.id))
        conn = Connection(user_a_id=a, user_b_id=b)
        db.add(conn)
    await db.delete(invite)
    await db.commit()
    await db.refresh(conn)
    return ConnectionOut(id=conn.id, partner=_person(inviter), created_at=conn.created_at)


# Connections


async def _partner_watching(conn: Connection, user: User) -> tuple[RoomState | None, bool]:
    """The room's episode when the partner is on it and the user isn't; whether they're online."""
    partner_id = conn.partner_of(user.id)
    members = {m["user_id"]: m for m in await rooms.presence(conn.id, [user.id, partner_id])}
    theirs = members.get(partner_id)
    room = await rooms.state(conn.id)
    watching = (
        room is not None
        and theirs is not None
        and (theirs.get("anime_id"), theirs.get("episode")) == (room["anime_id"], room["episode"])
        and user.id not in members
    )
    return (RoomState(**room) if watching else None), theirs is not None


@router.get("", response_model=list[ConnectionOut])
async def connections(user: CurrentUser, db: DB):
    found = await db.scalars(
        select(Connection)
        .where(or_(Connection.user_a_id == user.id, Connection.user_b_id == user.id))
        .order_by(Connection.created_at)
    )
    out = []
    for conn in found:
        partner = await db.get(User, conn.partner_of(user.id))
        if partner is None:
            continue
        watching, online = await _partner_watching(conn, user)
        cached = await together.cached(conn.id)
        out.append(
            ConnectionOut(
                id=conn.id,
                partner=_person(partner),
                created_at=conn.created_at,
                compatibility=cached["compatibility"]["score"] if cached else None,
                partner_watching=watching,
                partner_online=online,
            )
        )
    return out


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(connection_id: int, user: CurrentUser, db: DB) -> None:
    conn, _ = await _connection(db, connection_id, user)
    await db.delete(conn)
    await db.commit()
    await rooms.clear(connection_id)
    await together.forget(connection_id)


@router.get("/{connection_id}", response_model=TogetherOut)
async def recommendations(connection_id: int, user: CurrentUser, db: DB):
    """What to watch together, what to show each other, and how alike the two tastes are."""
    conn, partner = await _connection(db, connection_id, user)
    a, b = (user, partner) if user.id == conn.user_a_id else (partner, user)
    result = await together.report(db, conn.id, a, b)
    viewer_is_a = user.id == conn.user_a_id

    ids = {int(i) for i in result["pairs"]}
    shows = {s.id: s for s in await catalog.anime_by_ids(db, list(ids))}
    entries = {
        e.anime_id: e
        for e in await db.scalars(
            select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id.in_(ids))
        )
    }
    predictor = await predictor_for(db, user)

    def card(anime_id: int):
        anime: Anime = shows[anime_id]
        out = catalog.to_card(anime, entries.get(anime_id), predictor=predictor)
        pair = together.for_viewer(result["pairs"][str(anime_id)], viewer_is_a)
        out.pair = PairOut(**pair)
        return out

    names = {
        "show_to_partner": "show_to_b" if viewer_is_a else "show_to_a",
        "show_to_me": "show_to_a" if viewer_is_a else "show_to_b",
    }
    rows = []
    for row_id in ROW_ORDER:
        ids_in_row = result["rows"][names.get(row_id, row_id)]
        items = [card(i) for i in ids_in_row if i in shows]
        if items:
            rows.append(Row(id=row_id, title=row_id, items=items))
    compat = result["compatibility"]
    return TogetherOut(
        id=conn.id,
        me=_person(user),
        partner=_person(partner),
        compatibility=CompatibilityOut(
            **{k: v for k, v in compat.items() if k != "disagreements"},
            disagreements=[card(i) for i in compat["disagreements"] if i in shows],
        ),
        rows=rows,
        computed_at=result["computed_at"],
    )


# The synced player


@router.get("/{connection_id}/room", response_model=RoomOut)
async def room(connection_id: int, user: CurrentUser, db: DB):
    conn, partner = await _connection(db, connection_id, user)
    state = await rooms.state(conn.id)
    return RoomOut(
        state=state,
        members=await rooms.presence(conn.id, [user.id, partner.id]),
        now=rooms.now_ms(),
    )


@router.post("/{connection_id}/room", response_model=RoomOut)
async def update_room(connection_id: int, body: RoomUpdate, user: CurrentUser, db: DB):
    """Play, pause, seek or start an episode for both. Answers with the new state; the partner's
    player gets it as an event. 409 (with the room's state) when the room is on another
    episode than the change is for."""
    conn, partner = await _connection(db, connection_id, user)
    title = None
    if body.action == "load":
        anime = await catalog.get_anime(db, body.anime_id)
        if anime is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
        title = anime.title_en or anime.title
    try:
        state = await rooms.update(
            conn.id, user.id, body.action,
            anime_id=body.anime_id, episode=body.episode, position=body.position,
            playing=body.playing, title=title,
            stream=body.stream.model_dump() if body.stream else None,
        )  # fmt: skip
    except rooms.Conflict as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"message": "The room is on another episode", "state": e.room}
        ) from e
    return RoomOut(
        state=state,
        members=await rooms.presence(conn.id, [user.id, partner.id]),
        now=rooms.now_ms(),
    )


@router.get("/{connection_id}/room/events")
async def room_events(
    connection_id: int,
    request: Request,
    anime_id: int | None = Query(None),
    episode: int | None = Query(None),
) -> StreamingResponse:
    """Server-sent events: the room's state and presence, then every change. (No database
    session is held while it's open.)"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first")
    async with AsyncSessionLocal() as db:
        conn = await db.get(Connection, connection_id)
    if conn is None or user_id not in (conn.user_a_id, conn.user_b_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connection")
    stream = rooms.events(
        conn.id, user_id, [conn.user_a_id, conn.user_b_id], anime_id=anime_id, episode=episode
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        # no-transform: proxies (and Next's compression) mustn't buffer it.
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
