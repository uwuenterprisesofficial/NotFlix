from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from test_together import _connect
from test_together import people as together_people

from app.db.session import AsyncSessionLocal, sync_session
from app.models import Anime, Connection, FriendRecommendation, ListEntry, User
from app.services import together

pytestmark = pytest.mark.anyio

# The signed-in user and a second one (see test_together.py).
people = pytest.fixture(together_people.__wrapped__, name="people")


@pytest.fixture
def shows(database):
    with sync_session() as db:
        db.execute(delete(FriendRecommendation))
        db.execute(delete(Anime).where(Anime.id.in_([501, 502])))
        db.add_all(
            [
                Anime(id=501, title="Mushishi", genres=["Mystery"], status="finished_airing",
                      num_episodes=26, mal_details_at=datetime.now(UTC),
                      enriched_at=datetime.now(UTC)),
                Anime(id=502, title="Ping Pong", genres=["Sports"], status="finished_airing",
                      num_episodes=11, mal_details_at=datetime.now(UTC),
                      enriched_at=datetime.now(UTC)),
            ]
        )  # fmt: skip
        db.commit()


async def test_recommend_a_show_to_a_friend(client, people, shows):
    conn = await _connect(client, people)
    resp = await client.post(
        "/friends/recommendations",
        json={"anime_id": 501, "connection_ids": [conn], "message": "  So calm, watch it!  "},
    )
    assert resp.status_code == 200
    [friend] = resp.json()["friends"]
    assert friend["person"]["name"] == "anna" and friend["recommended_at"] is not None
    assert friend["their_progress"] is None

    # Anna finds it: in her list of recommendations, on her home page, and as a badge.
    people.act_as(people.other)
    body = (await client.get("/friends/recommendations")).json()
    [received] = body["received"]
    assert received["person"]["name"] == "tester"
    assert received["anime"]["id"] == 501
    assert received["message"] == "So calm, watch it!"
    assert (received["seen"], body["unseen"], body["sent"]) == (False, 1, [])
    assert (await client.get("/me")).json()["recommendations_unseen"] == 1
    rows = {r["id"]: r for r in (await client.get("/browse")).json()["rows"]}
    [card] = rows["from-friends"]["items"]
    assert (card["id"], card["reason"]) == (501, "friend:tester")
    # On the show's page: who recommended it.
    show = (await client.get("/friends/recommendations/anime/501")).json()
    assert [r["person"]["name"] for r in show["received"]] == ["tester"]
    assert show["friends"][0]["recommended_at"] is None  # she didn't recommend it to him

    assert (await client.post("/friends/recommendations/seen")).status_code == 204
    assert (await client.get("/friends/recommendations")).json()["unseen"] == 0

    # She starts watching: he sees where she is with it.
    with sync_session() as db:
        db.add(ListEntry(user_id=people.other.id, anime_id=501, status="watching",
                         episodes_watched=3, score=0))  # fmt: skip
        db.commit()
    people.act_as(people.me)
    [sent] = (await client.get("/friends/recommendations")).json()["sent"]
    assert sent["person"]["name"] == "anna"
    assert sent["their_progress"] == {
        "status": "watching", "episodes_watched": 3, "score": 0, "failed": []
    }  # fmt: skip

    # Recommending it again counts as new for her, with the new note.
    await client.post("/friends/recommendations", json={"anime_id": 501, "connection_ids": [conn]})
    people.act_as(people.other)
    body = (await client.get("/friends/recommendations")).json()
    assert body["unseen"] == 1 and body["received"][0]["message"] is None
    with sync_session() as db:
        assert db.scalar(select(FriendRecommendation.id).where(
            FriendRecommendation.anime_id == 501)) is not None  # fmt: skip
        assert len(db.scalars(select(FriendRecommendation)).all()) == 1


async def test_putting_aside_and_taking_back(client, people, shows):
    conn = await _connect(client, people)
    for anime_id in (501, 502):
        await client.post(
            "/friends/recommendations", json={"anime_id": anime_id, "connection_ids": [conn]}
        )
    people.act_as(people.other)
    received = (await client.get("/friends/recommendations")).json()["received"]
    assert [r["anime"]["id"] for r in received] == [502, 501]
    first, second = received
    # "Not for me": gone for her, marked for him.
    resp = await client.delete(f"/friends/recommendations/{first['id']}")
    assert resp.status_code == 204
    left = (await client.get("/friends/recommendations")).json()
    assert [r["id"] for r in left["received"]] == [second["id"]] and left["unseen"] == 1

    people.act_as(people.me)
    sent = {
        r["anime"]["id"]: r for r in (await client.get("/friends/recommendations")).json()["sent"]
    }
    assert sent[502]["dismissed"] is True and sent[501]["dismissed"] is False
    # He takes the other one back.
    assert (await client.delete(f"/friends/recommendations/{second['id']}")).status_code == 204
    people.act_as(people.other)
    assert (await client.get("/friends/recommendations")).json()["received"] == []


async def test_only_to_friends(client, people, shows):
    conn = await _connect(client, people)
    with sync_session() as db:
        stranger = User(name="x", mal_user_id=99, access_token="a")
        db.add(stranger)
        db.commit()
        db.refresh(stranger)
        a, b = sorted((stranger.id, people.other.id))
        other = Connection(user_a_id=a, user_b_id=b)
        db.add(other)
        db.commit()
        db.refresh(other)
    resp = await client.post(
        "/friends/recommendations", json={"anime_id": 501, "connection_ids": [conn, other.id]}
    )
    assert resp.status_code == 404
    unknown = await client.post(
        "/friends/recommendations", json={"anime_id": 999999, "connection_ids": [conn]}
    )
    assert unknown.status_code == 404
    with sync_session() as db:
        assert db.scalars(select(FriendRecommendation)).all() == []
    # Someone else's recommendation can't be removed.
    await client.post("/friends/recommendations", json={"anime_id": 501, "connection_ids": [conn]})
    people.act_as(stranger)
    with sync_session() as db:
        rec_id = db.scalar(select(FriendRecommendation.id))
    assert (await client.delete(f"/friends/recommendations/{rec_id}")).status_code == 404


async def test_disconnecting_hides_them(client, people, shows):
    conn = await _connect(client, people)
    await client.post("/friends/recommendations", json={"anime_id": 501, "connection_ids": [conn]})
    await client.delete(f"/together/{conn}")
    people.act_as(people.other)
    body = (await client.get("/friends/recommendations")).json()
    assert (body["received"], body["unseen"]) == ([], 0)
    rows = {r["id"] for r in (await client.get("/browse")).json()["rows"]}
    assert "from-friends" not in rows


async def test_a_guests_recommendations_move_to_their_account(database, people, shows):
    with sync_session() as db:
        guest = User(name="Sam", is_guest=True)
        db.add(guest)
        db.commit()
        now = datetime.now(UTC)
        db.add_all(
            [
                FriendRecommendation(from_user_id=guest.id, to_user_id=people.other.id,
                                     anime_id=501, created_at=now),
                FriendRecommendation(from_user_id=people.other.id, to_user_id=guest.id,
                                     anime_id=502, created_at=now),
                # Already recommended by the account itself: the guest's copy goes.
                FriendRecommendation(from_user_id=people.me.id, to_user_id=people.other.id,
                                     anime_id=501, created_at=now, message="mine"),
            ]
        )  # fmt: skip
        db.commit()
        guest_id = guest.id
    async with AsyncSessionLocal() as db:
        guest = await db.get(User, guest_id)
        me = await db.get(User, people.me.id)
        await together.absorb_guest(db, guest, me)
        await db.commit()
    with sync_session() as db:
        found = {
            (r.from_user_id, r.to_user_id, r.anime_id, r.message)
            for r in db.scalars(select(FriendRecommendation))
        }
    assert found == {
        (people.me.id, people.other.id, 501, "mine"),
        (people.other.id, people.me.id, 502, None),
    }
