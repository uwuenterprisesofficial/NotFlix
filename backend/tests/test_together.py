import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete
from test_anilist_accounts import _sign_in, clean, providers  # noqa: F401 (fixtures)

from app.db.session import sync_session
from app.models import Anime, Connection, ConnectionInvite, ListEntry, User

pytestmark = pytest.mark.anyio

ACTION, ROMANCE, SPORTS, HORROR = (
    {"id": 1, "name": "Action"},
    {"id": 22, "name": "Romance"},
    {"id": 30, "name": "Sports"},
    {"id": 14, "name": "Horror"},
)


@pytest.fixture
def people(database, user):
    """The signed-in user plus a second one; `people.act_as(u)` switches who's signed in."""
    from app.api.deps import current_user_optional
    from app.main import app

    with sync_session() as db:
        db.execute(delete(ConnectionInvite))
        db.execute(delete(Connection))
        db.execute(delete(User).where(User.id != user.id))
        partner = User(
            name="anna", anilist_user_id=7, anilist_name="anna", anilist_token="t",
            last_synced_at=datetime(2026, 9, 1, tzinfo=UTC),
        )  # fmt: skip
        db.add(partner)
        db.commit()
        db.refresh(partner)

    class People:
        me, other = user, partner

        def act_as(self, u):
            app.dependency_overrides[current_user_optional] = lambda: u

    return People()


async def _connect(client, people) -> int:
    code = (await client.post("/together/invites")).json()["code"]
    people.act_as(people.other)
    conn = (await client.post(f"/together/invites/{code}/accept")).json()
    people.act_as(people.me)
    return conn["id"]


async def test_invite_and_connect(client, people):
    invite = (await client.post("/together/invites")).json()
    info = (await client.get(f"/together/invites/{invite['code']}")).json()
    assert info["inviter"]["name"] == "tester" and info["own"] is True
    assert (await client.post(f"/together/invites/{invite['code']}/accept")).status_code == 409

    people.act_as(people.other)
    info = (await client.get(f"/together/invites/{invite['code']}")).json()
    assert info["own"] is False and info["connection_id"] is None
    conn = (await client.post(f"/together/invites/{invite['code']}/accept")).json()
    assert conn["partner"]["name"] == "tester"
    # Used once.
    assert (await client.get(f"/together/invites/{invite['code']}")).status_code == 404
    [mine] = (await client.get("/together")).json()
    assert mine["partner"]["name"] == "tester"

    people.act_as(people.me)
    [mine] = (await client.get("/together")).json()
    assert mine["partner"]["name"] == "anna" and mine["id"] == conn["id"]
    # Someone else's connection doesn't exist for a third user.
    with sync_session() as db:
        stranger = User(name="x", mal_user_id=99, access_token="a")
        db.add(stranger)
        db.commit()
        db.refresh(stranger)
    people.act_as(stranger)
    assert (await client.get(f"/together/{conn['id']}")).status_code == 404
    assert (await client.get(f"/together/{conn['id']}/room")).status_code == 404

    people.act_as(people.me)
    assert (await client.delete(f"/together/{conn['id']}")).status_code == 204
    assert (await client.get("/together")).json() == []


async def test_expired_invite(client, people):
    with sync_session() as db:
        db.add(ConnectionInvite(
            code="old", user_id=people.me.id, expires_at=datetime.now(UTC) - timedelta(hours=1)
        ))  # fmt: skip
        db.commit()
    people.act_as(people.other)
    assert (await client.post("/together/invites/old/accept")).status_code == 404


@pytest.fixture
def lists(people):
    """tester loves action and sports, anna loves action and romance."""
    shows = {
        # id: (tags, tester's status/score, anna's status/score)
        1: ([ACTION], ("completed", 9), ("completed", 9)),
        2: ([ACTION], ("completed", 10), ("completed", 8)),
        3: ([SPORTS], ("completed", 10), None),  # tester's favourite, anna hasn't seen it
        4: ([ROMANCE], None, ("completed", 10)),  # anna's favourite, tester hasn't seen it
        5: ([HORROR], ("completed", 3), ("completed", 9)),  # they disagree
        6: ([ROMANCE], ("completed", 6), ("completed", 9)),
        7: ([SPORTS], ("completed", 8), ("completed", 5)),
        8: ([ACTION, ROMANCE], None, None),  # new to both, both would like it
        9: ([HORROR], None, None),  # new to both, tester wouldn't
        10: ([ACTION], ("watching", 0), ("watching", 0)),
        11: ([ACTION], ("plan_to_watch", 0), ("plan_to_watch", 0)),
    }
    with sync_session() as db:
        db.execute(delete(ListEntry))
        for i, (tags, *_rest) in shows.items():
            db.merge(Anime(
                id=i, title=f"Show {i}", genres=[t["name"] for t in tags], genre_tags=tags,
                num_list_users=100_000 - i, mean=7.5, media_type="tv",
            ))  # fmt: skip
        for i, (_, mine, theirs) in shows.items():
            for u, entry in ((people.me, mine), (people.other, theirs)):
                if entry:
                    db.add(ListEntry(user_id=u.id, anime_id=i, status=entry[0], score=entry[1]))
        db.commit()
    from redis import Redis

    from app.core.config import get_settings

    r = Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("together:*"):
        r.delete(key)
    return shows


async def test_recommendations_for_both(client, people, lists):
    cid = await _connect(client, people)
    body = (await client.get(f"/together/{cid}")).json()
    assert body["partner"]["name"] == "anna"
    rows = {r["id"]: [c["id"] for c in r["items"]] for r in body["rows"]}
    assert rows["show_to_partner"] == [3]  # tester's favourite anna hasn't seen
    assert rows["show_to_me"] == [4]
    assert 8 in rows["together"] and 9 not in rows["together"]
    assert rows["continue"] == [10]
    assert rows["planned"] == [11]
    assert rows["both_loved"] == [1]  # anna gave show 2 an 8

    card = next(c for r in body["rows"] if r["id"] == "show_to_me" for c in r["items"])
    assert card["pair"]["partner"]["score"] == 10 and card["pair"]["me"]["status"] is None

    compat = body["compatibility"]
    assert compat["shared"] == 6 and compat["both_scored"] == 5
    assert 0 <= compat["score"] <= 100
    assert compat["disagreements"][0]["id"] == 5
    assert "Action" in compat["shared_genres"]

    # The other side sees the same, mirrored.
    people.act_as(people.other)
    body = (await client.get(f"/together/{cid}")).json()
    rows = {r["id"]: [c["id"] for c in r["items"]] for r in body["rows"]}
    assert rows["show_to_partner"] == [4] and rows["show_to_me"] == [3]
    assert (await client.get("/together")).json()[0]["compatibility"] == compat["score"]


async def test_synced_room(client, people, lists):
    cid = await _connect(client, people)
    room = (await client.get(f"/together/{cid}/room")).json()
    assert room["state"] is None and room["members"] == []

    load = {"action": "load", "anime_id": 1, "episode": 3, "position": 0}
    state = (await client.post(f"/together/{cid}/room", json=load)).json()["state"]
    assert state["title"] == "Show 1" and state["playing"] is False
    first_rev = state["rev"]

    people.act_as(people.other)
    play = {"action": "play", "anime_id": 1, "episode": 3, "position": 12.5}
    state = (await client.post(f"/together/{cid}/room", json=play)).json()["state"]
    assert state["playing"] is True and state["position"] == 12.5
    assert state["rev"] > first_rev and state["by"] == people.other.id
    assert state["title"] == "Show 1"

    # A change for another episode: the room moved on.
    stale = {"action": "pause", "anime_id": 1, "episode": 2, "position": 30}
    res = await client.post(f"/together/{cid}/room", json=stale)
    assert res.status_code == 409 and res.json()["detail"]["state"]["episode"] == 3

    seek = {"action": "seek", "anime_id": 1, "episode": 3, "position": 300}
    state = (await client.post(f"/together/{cid}/room", json=seek)).json()["state"]
    assert state["position"] == 300 and state["playing"] is True  # keeps playing


async def test_room_events_and_presence(client, people, lists):
    from app.services import rooms

    cid = await _connect(client, people)
    ids = [people.me.id, people.other.id]
    stream = rooms.events(cid, people.other.id, ids, anime_id=1, episode=3)

    async def next_event():
        while True:
            chunk = await asyncio.wait_for(anext(stream), 5)
            if chunk.startswith("data: "):
                return json.loads(chunk[6:])

    assert (await next_event())["state"] is None
    presence = await next_event()
    assert (await next_event())["type"] == "presence"  # anna's arrival, as published
    assert presence["members"] == [{"user_id": people.other.id, "anime_id": 1, "episode": 3}]

    # tester (not in the room) is told anna is watching, once the room is on that episode.
    await rooms.update(cid, people.other.id, "load", anime_id=1, episode=3, position=0,
                       title="Show 1")  # fmt: skip
    event = await next_event()
    assert event["type"] == "state" and event["state"]["episode"] == 3
    [conn] = (await client.get("/together")).json()
    assert conn["partner_online"] is True
    assert conn["partner_watching"]["title"] == "Show 1"

    await rooms.update(cid, people.me.id, "pause", anime_id=1, episode=3, position=42.0)
    event = await next_event()
    assert event["state"]["action"] == "pause" and event["state"]["position"] == 42.0

    await stream.aclose()  # leaving removes the presence
    assert await rooms.presence(cid, ids) == []


async def test_expected_position():
    from app.services.rooms import expected_position

    room = {"position": 10.0, "playing": True, "at": 1_000_000}
    assert expected_position(room, 1_002_500) == 12.5
    assert expected_position({**room, "playing": False}, 1_002_500) == 10.0


# Guests


async def test_recommendations_with_a_guest(client, people, lists):
    with sync_session() as db:
        db.execute(delete(ListEntry).where(ListEntry.user_id == people.other.id))
        guest = db.get(User, people.other.id)
        guest.is_guest = True
        db.commit()
    people.other.is_guest = True
    cid = await _connect(client, people)

    body = (await client.get(f"/together/{cid}")).json()
    assert body["me_list"] is True and body["partner_list"] is False
    rows = {r["id"]: [c["id"] for c in r["items"]] for r in body["rows"]}
    # Only tester's list: their favourites for the guest, what they're watching and planned.
    assert set(rows["show_to_partner"]) == {1, 2, 3}
    assert "show_to_me" not in rows and "both_loved" not in rows
    assert rows["continue"] == [10] and rows["planned"] == [11]
    assert 8 in rows["together"]
    card = body["rows"][0]["items"][0]
    assert card["pair"]["partner"] is None and card["pair"]["me"] is not None
    assert body["compatibility"]["score"] is None

    people.act_as(people.other)
    body = (await client.get(f"/together/{cid}")).json()
    rows = {r["id"]: [c["id"] for c in r["items"]] for r in body["rows"]}
    assert set(rows["show_to_me"]) == {1, 2, 3}
    # A guest has no list of their own.
    assert (await client.put("/anime/1/progress", json={"episodes_watched": 1})).status_code == 403
    assert (await client.post("/me/sync")).status_code == 403
    assert (await client.get("/me/stats")).status_code == 403


async def test_no_lists_at_all(client, people, lists):
    with sync_session() as db:
        db.execute(delete(ListEntry))
        db.commit()
    cid = await _connect(client, people)
    body = (await client.get(f"/together/{cid}")).json()
    assert body["me_list"] is False and body["partner_list"] is False
    rows = {r["id"]: [c["id"] for c in r["items"]] for r in body["rows"]}
    assert set(rows) == {"top_rated", "popular"}
    popular = rows["popular"]
    assert popular.index(1) < popular.index(11)  # by members


async def test_disconnecting_removes_the_guest(client, people):
    with sync_session() as db:
        db.get(User, people.other.id).is_guest = True
        db.commit()
    people.other.is_guest = True
    cid = await _connect(client, people)
    assert (await client.delete(f"/together/{cid}")).status_code == 204
    with sync_session() as db:
        assert db.get(User, people.other.id) is None
        assert db.get(User, people.me.id) is not None


async def _join_as_guest(client, name="Sam"):
    await _sign_in(client, "mal")
    code = (await client.post("/together/invites")).json()["code"]
    await client.post("/auth/logout")
    res = await client.post(f"/together/invites/{code}/guest", json={"name": name})
    assert res.status_code == 200 and res.json()["partner"]["name"] == "mal-user"
    return res.json()["id"]


@pytest.mark.usefixtures("providers")
async def test_guest_signs_in_and_keeps_the_connection(client):
    cid = await _join_as_guest(client)
    me = (await client.get("/me")).json()
    assert (me["name"], me["guest"], me["mal"], me["anilist"]) == ("Sam", True, None, None)
    [conn] = (await client.get("/together")).json()
    assert conn["id"] == cid
    # Signed in already: joining as a guest again isn't possible.
    assert (await client.post("/together/invites/x/guest", json={"name": "a"})).status_code == 409

    # Signing in (an account nobody has yet) turns the guest into that account's user.
    await _sign_in(client, "anilist")
    after = (await client.get("/me")).json()
    assert after["id"] == me["id"] and after["guest"] is False
    assert after["name"] == "al-user" and after["anilist"] == {"name": "al-user"}
    assert [c["id"] for c in (await client.get("/together")).json()] == [cid]


@pytest.mark.usefixtures("providers")
async def test_guest_signs_in_with_an_existing_account(client):
    await _sign_in(client, "anilist")  # al-user exists already
    owner = (await client.get("/me")).json()
    await client.post("/auth/logout")
    cid = await _join_as_guest(client)
    guest_id = (await client.get("/me")).json()["id"]

    await _sign_in(client, "anilist")
    me = (await client.get("/me")).json()
    assert me["id"] == owner["id"] and me["guest"] is False
    [conn] = (await client.get("/together")).json()
    assert conn["id"] == cid and conn["partner"]["name"] == "mal-user"
    with sync_session() as db:
        assert db.get(User, guest_id) is None
