import json

import pytest
from sqlalchemy import delete

from app.db.session import sync_session
from app.models import Anime, ListEntry, PlaybackPosition

pytestmark = pytest.mark.anyio


@pytest.fixture
def show(database, user):
    with sync_session() as db:
        db.execute(delete(PlaybackPosition))
        db.execute(delete(ListEntry))
        db.merge(Anime(id=5, title="Five", genres=[], num_episodes=12))
        db.add(ListEntry(user_id=user.id, anime_id=5, status="watching", episodes_watched=2))
        db.commit()


async def test_resume_the_current_episode(client, user, show):
    assert (await client.get("/anime/5/position")).json() is None
    body = {"episode": 3, "position_s": 734.4, "duration_s": 1420}
    assert (await client.put("/anime/5/position", json=body)).status_code == 204
    saved = (await client.get("/anime/5/position")).json()
    assert saved == {"episode": 3, "position_s": 734.4, "duration_s": 1420.0}
    assert (await client.get("/anime/5")).json()["resume"]["position_s"] == 734.4
    # On the home page's Continue Watching card too.
    rows = {r["id"]: r for r in (await client.get("/browse")).json()["rows"]}
    [card] = rows["continue"]["items"]
    assert card["resume"]["episode"] == 3

    # The next episode replaces it (one per show)...
    await client.post("/anime/5/position", content=json.dumps(
        {"episode": 4, "position_s": 60, "duration_s": 1420}),
        headers={"content-type": "application/json"})  # fmt: skip
    assert (await client.get("/anime/5/position")).json()["episode"] == 4
    # ...the first seconds don't count...
    await client.put("/anime/5/position", json={"episode": 5, "position_s": 3})
    assert (await client.get("/anime/5/position")).json()["episode"] == 4
    # ...and reaching the credits finishes it.
    await client.put(
        "/anime/5/position", json={"episode": 4, "position_s": 1350, "duration_s": 1420}
    )
    assert (await client.get("/anime/5/position")).json() is None


async def test_marking_watched_clears_it(client, user, show, monkeypatch):
    from app.services import mal

    async def update(self, anime_id, **fields):
        return {"status": "watching", "num_episodes_watched": fields["num_watched_episodes"]}

    monkeypatch.setattr(mal.MalClient, "update_my_list_status", update)
    await client.put("/anime/5/position", json={"episode": 3, "position_s": 500})
    await client.put("/anime/5/progress", json={"episodes_watched": 3})
    assert (await client.get("/anime/5/position")).json() is None


async def test_positions_need_an_account(client, database):
    assert (await client.get("/anime/5/position")).status_code == 401
