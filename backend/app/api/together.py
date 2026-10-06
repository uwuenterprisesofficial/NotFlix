"""Watch Together: connect with someone (an invite link), get recommendations for both of you,
and watch with a synced player (a room per connection, followed through server-sent events).

Someone without an account joins as a guest: an invite link and a name make a guest user
(signed in by the session cookie like anyone else) who has no list. The recommendations then
use only the other's list, or none. Signing in later (or linking a list) keeps the guest's
connections.
"""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select, update

from app.api.deps import DB, CurrentUser, OptionalUser
from app.db.session import AsyncSessionLocal
from app.models import Anime, Connection, ConnectionInvite, ListEntry, User
from app.schemas import (
    CompatibilityOut,
    ConnectionOut,
    FriendCodeIn,
    FriendCodeOut,
    GuestIn,
    InviteInfo,
    InviteOut,
    PairOut,
    PersonOut,
    RoomOut,
    RoomState,
    RoomUpdate,
    Row,
    SessionOut,
    TogetherOut,
)
from app.services import catalog, rooms, together
from app.services.taste import predictor_for

router = APIRouter(prefix="/together", tags=["together"])

INVITE_TTL = timedelta(days=7)
ROW_ORDER = [
    "continue", "together", "planned", "show_to_partner", "show_to_me", "both_loved",
    "top_rated", "popular",
]  # fmt: skip


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


@router.post("/invites/{code}/guest", response_model=ConnectionOut)
async def join_as_guest(code: str, body: GuestIn, request: Request, user: OptionalUser, db: DB):
    """Accept an invite without an account: a guest with this name, signed in from now on."""
    if user is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already signed in: accept the invite")
    invite, inviter = await _invite(db, code)
    guest = User(name=body.name.strip() or "Guest", is_guest=True)
    db.add(guest)
    await db.flush()
    request.session["user_id"] = guest.id
    return await _accept(db, invite, inviter, guest)


@router.post("/invites/{code}/accept", response_model=ConnectionOut)
async def accept_invite(code: str, user: CurrentUser, db: DB):
    invite, inviter = await _invite(db, code)
    return await _accept(db, invite, inviter, user)


async def _accept(db: DB, invite: ConnectionInvite, inviter: User, user: User) -> ConnectionOut:
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
    online = theirs is not None or await rooms.online(partner_id)
    return (RoomState(**room) if watching else None), online


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
        out.append(
            ConnectionOut(
                id=conn.id,
                partner=_person(partner),
                created_at=conn.created_at,
                compatibility=await together.score(conn.id),
                partner_watching=watching,
                partner_online=online,
            )
        )
    return out


# Sessions: watching together for real (see services/rooms.py)


async def _session_out(conn: Connection, partner: User, joined: list[int]) -> SessionOut:
    pair = {conn.user_a_id, conn.user_b_id}
    return SessionOut(
        connection_id=conn.id, partner=_person(partner), joined=joined,
        active=pair <= set(joined),
    )  # fmt: skip


async def _pair(conn: Connection) -> list[int]:
    return [conn.user_a_id, conn.user_b_id]


@router.get("/sessions", response_model=list[SessionOut])
async def my_sessions(user: CurrentUser, db: DB):
    """The user's sessions anyone joined: invitations (only the partner joined), ones waiting
    for the partner, and the active one. (Asked for every few seconds: the user is online.)"""
    await rooms.seen(user.id)
    conns = (
        await db.scalars(
            select(Connection).where(
                or_(Connection.user_a_id == user.id, Connection.user_b_id == user.id)
            )
        )
    ).all()
    found = await rooms.sessions([c.id for c in conns])
    out = []
    for conn in conns:
        if conn.id in found and (partner := await db.get(User, conn.partner_of(user.id))):
            out.append(await _session_out(conn, partner, found[conn.id]))
    return out


@router.post("/{connection_id}/session", response_model=SessionOut)
async def join_session(connection_id: int, user: CurrentUser, db: DB):
    """Start a session with this connection (inviting them), or join the one they started.
    Any other session of the user ends."""
    conn, partner = await _connection(db, connection_id, user)
    others = await db.scalars(
        select(Connection.id).where(
            or_(Connection.user_a_id == user.id, Connection.user_b_id == user.id),
            Connection.id != conn.id,
        )
    )
    for other_id, joined in (await rooms.sessions(list(others))).items():
        if user.id in joined:
            await rooms.leave(other_id)
    joined = await rooms.join(conn.id, user.id, await _pair(conn))
    return await _session_out(conn, partner, joined)


@router.delete("/{connection_id}/session", status_code=status.HTTP_204_NO_CONTENT)
async def leave_session(connection_id: int, user: CurrentUser, db: DB) -> None:
    """Leave the session (or turn down the invitation): it ends for both."""
    conn, _ = await _connection(db, connection_id, user)
    await rooms.leave(conn.id)


# Friend codes: connecting without a link


FRIEND_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # nothing to misread (0/O, 1/I)
FRIEND_CODE_LENGTH = 8


def _format_code(raw: str) -> str:
    return f"{raw[:4]}-{raw[4:]}"


def _normalize_code(code: str) -> str:
    return "".join(c for c in code.upper() if c in FRIEND_CODE_ALPHABET)


async def _new_code(db: DB, user: User) -> str:
    while True:
        raw = "".join(secrets.choice(FRIEND_CODE_ALPHABET) for _ in range(FRIEND_CODE_LENGTH))
        if not await db.scalar(select(User.id).where(User.friend_code == raw)):
            await db.execute(update(User).where(User.id == user.id).values(friend_code=raw))
            await db.commit()
            user.friend_code = raw
            return raw


@router.get("/code", response_model=FriendCodeOut)
async def friend_code(user: CurrentUser, db: DB):
    """The user's friend code: whoever enters it is connected with them."""
    raw = user.friend_code or await _new_code(db, user)
    return FriendCodeOut(code=_format_code(raw))


@router.post("/code", response_model=FriendCodeOut)
async def new_friend_code(user: CurrentUser, db: DB):
    """A new code: the old one stops working."""
    return FriendCodeOut(code=_format_code(await _new_code(db, user)))


@router.post("/connect", response_model=ConnectionOut)
async def connect_by_code(body: FriendCodeIn, user: CurrentUser, db: DB):
    """Connect with the owner of a friend code."""
    raw = _normalize_code(body.code)
    other = await db.scalar(select(User).where(User.friend_code == raw)) if raw else None
    if other is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No one has this code")
    if other.id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "That's your own code")
    conn = await _between(db, user.id, other.id)
    if conn is None:
        a, b = sorted((user.id, other.id))
        conn = Connection(user_a_id=a, user_b_id=b)
        db.add(conn)
        await db.commit()
        await db.refresh(conn)
    return ConnectionOut(id=conn.id, partner=_person(other), created_at=conn.created_at)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(connection_id: int, user: CurrentUser, db: DB) -> None:
    conn, partner = await _connection(db, connection_id, user)
    await db.delete(conn)
    await db.flush()
    # A guest is only there to watch with someone: without any connection left, they're gone.
    for person in (user, partner):
        if person.is_guest and not await _connection_count(db, person.id):
            await db.delete(person)
    await db.commit()
    await rooms.clear(connection_id)
    await rooms.leave(connection_id)
    await together.forget(connection_id)


async def _connection_count(db: DB, user_id: int) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(Connection)
        .where(or_(Connection.user_a_id == user_id, Connection.user_b_id == user_id))
    )


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
        ids_in_row = result["rows"].get(names.get(row_id, row_id), [])
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
        me_list=result["lists"]["a" if viewer_is_a else "b"],
        partner_list=result["lists"]["b" if viewer_is_a else "a"],
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
