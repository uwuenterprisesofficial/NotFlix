import pytest
from sqlalchemy import delete

from app.db.session import sync_session
from app.models import Anime, ListEntry, SkipSegment, StreamSource

pytestmark = pytest.mark.anyio


@pytest.fixture
def show(database):
    from redis import Redis

    from app.core.config import get_settings

    for key in Redis.from_url(get_settings().redis_url).scan_iter("preview:miss:*"):
        Redis.from_url(get_settings().redis_url).delete(key)
    with sync_session() as db:
        for model in (StreamSource, SkipSegment, ListEntry):
            db.execute(delete(model))
        db.execute(delete(Anime).where(Anime.id.in_([5, 6])))
        db.add(Anime(id=5, title="Five", genres=["Action"], num_episodes=12,
                     status="finished_airing"))  # fmt: skip
        db.add(Anime(id=6, title="Six", genres=[], status="not_yet_aired"))
        for language, url in (
            ("en-sub", "https://cdn.x/en.mp4"),
            ("de-sub", "https://cdn.x/de.mp4"),
        ):
            db.add(StreamSource(anime_id=5, episode=1, provider=f"p-{language}", kind="direct",
                                url=url, language=language))  # fmt: skip
        db.add(SkipSegment(anime_id=5, episode=1, kind="opening", start_s=85.2, end_s=175,
                           confidence=0.9, source="analysis"))  # fmt: skip
        db.commit()


async def test_preview_plays_episode_one_from_its_opening(client, show):
    # Nothing found for episode 1 yet: no preview, and no scan is started for it.
    assert (await client.get("/anime/5/preview")).status_code == 404
    await client.get("/anime/5/episodes/1/sources")  # what the show page/player would do

    en = (await client.get("/anime/5/preview", params={"lang": "en"})).json()
    assert (en["episode"], en["language"], en["start_s"]) == (1, "en-sub", 85.2)
    assert en["url"] == "https://cdn.x/en.mp4"
    de = (await client.get("/anime/5/preview", params={"lang": "de"})).json()
    assert de["language"] == "de-sub"


async def test_no_preview_before_the_first_episode_airs(client, show):
    assert (await client.get("/anime/6/preview")).status_code == 404


async def test_plan_to_watch_goes_to_the_linked_list(client, user, show, monkeypatch):
    from app.services import mal

    written = []

    async def update(self, anime_id, **fields):
        written.append((anime_id, fields))
        return {"status": fields["status"], "num_episodes_watched": 0, "score": 0}

    monkeypatch.setattr(mal.MalClient, "update_my_list_status", update)
    body = (await client.put("/anime/5/list", json={"status": "plan_to_watch"})).json()
    assert body["status"] == "plan_to_watch" and body["failed"] == []
    assert written == [(5, {"status": "plan_to_watch"})]  # progress isn't touched
    card = (await client.get("/anime/5")).json()
    assert card["progress"]["status"] == "plan_to_watch"
    assert (card["status"], card["num_episodes"]) == ("finished_airing", 12)
    assert (await client.put("/anime/5/list", json={"status": "nope"})).status_code == 422
