import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.core.cache import redis
from app.db.session import sync_session
from app.models import Anime, ListEntry

pytestmark = pytest.mark.anyio


def _row(
    mal_id: int,
    title: str,
    media_type: str = "tv",
    status: str = "finished_airing",
    mean: float | None = None,
) -> dict:
    return {"id": mal_id, "title": title, "media_type": media_type, "genres": [],
            "status": status, "mean": mean}  # fmt: skip


@pytest.fixture
def listed(user):
    now = datetime.now(UTC)
    with sync_session() as db:
        db.execute(delete(ListEntry))
        db.execute(delete(Anime))
        db.add_all([
            Anime(id=1, title="Airing show", genres=[], status="currently_airing"),
            Anime(id=2, title="Finished show", genres=[], status="finished_airing"),
            Anime(id=3, title="Planned show", genres=[], status="finished_airing", mean=6.5),
            Anime(id=4, title="Planned and airing", genres=[], status="currently_airing",
                  mean=8.1),
        ])  # fmt: skip
        statuses = ((1, "watching"), (2, "completed"), (3, "plan_to_watch"), (4, "plan_to_watch"))
        for ago, (anime_id, status) in enumerate(statuses, start=1):
            db.add(ListEntry(
                user_id=user.id, anime_id=anime_id, status=status, score=0, episodes_watched=0,
                updated_at=now - timedelta(days=ago),
            ))  # fmt: skip
        db.commit()


async def test_my_list_sections(client, listed, monkeypatch):
    from app.services import catalog_jobs, related

    fetched: list[list[int]] = []

    async def fetch(ids, http=None):
        fetched.append(ids)

    monkeypatch.setattr(related, "fetch", fetch)
    monkeypatch.setattr(catalog_jobs, "enqueue", lambda *a, **k: _none())
    # "Finished show" has a film and a sequel; its prequel is the planned show (not offered:
    # it's in Plan to watch) and the airing one is being watched.
    await redis().set("related:2", json.dumps([
        {"relation": "SIDE_STORY", "row": _row(50, "The Film", "movie", mean=7.0)},
        {"relation": "SEQUEL", "row": _row(51, "Season 2", mean=8.5)},
        {"relation": "SEQUEL", "row": _row(52, "Season 3", status="not_yet_aired")},
        {"relation": "PREQUEL", "row": _row(3, "Planned show")},
        {"relation": "SEQUEL", "row": _row(1, "Airing show")},
    ]))  # fmt: skip
    await redis().delete("related:1")

    body = (await client.get("/me/library")).json()
    sections = {s["id"]: [a["id"] for a in s["items"]] for s in body["sections"]}
    # Each section by how much the user should like it (here MAL's score: no predictions), and
    # what's related split into what has aired and what's still to come.
    assert sections == {
        "continue": [1], "season": [4, 1], "planned": [4, 3], "related": [51, 50],
        "related_upcoming": [52],
    }  # fmt: skip
    related_cards = next(s for s in body["sections"] if s["id"] == "related")["items"]
    assert related_cards[1]["reason"] == "related:SIDE_STORY:Finished show"
    assert related_cards[1]["media_type"] == "movie"
    # The airing show's relations weren't cached: fetched in the background.
    assert body["related_pending"] is True or fetched == [[1]]
    await related.wait_idle()
    assert fetched == [[1]]
    await redis().delete("related:2")


async def _none():
    return None


async def test_up_next_after_the_last_episode(client, listed, monkeypatch):
    from app.models import Recommendation
    from app.services import catalog_jobs

    monkeypatch.setattr(catalog_jobs, "enqueue", lambda *a, **k: _none())
    with sync_session() as db:
        db.execute(delete(Recommendation))
        db.add_all([
            Anime(id=60, title="Recommended", genres=[], status="finished_airing"),
            Anime(id=61, title="Recommended too", genres=[], status="finished_airing"),
            Anime(id=62, title="Season 2", genres=[], status="finished_airing"),
        ])  # fmt: skip
        user_id = db.scalar(select(ListEntry.user_id))
        db.add_all([
            Recommendation(user_id=user_id, anime_id=61, score=0.5, reason="Because you liked X"),
            Recommendation(user_id=user_id, anime_id=60, score=0.9, reason="Because you liked Y"),
        ])  # fmt: skip
        db.commit()
    # The finished show has an unseen sequel: that's next.
    await redis().set("related:2", json.dumps([
        {"relation": "SEQUEL", "row": _row(62, "Season 2")},
        {"relation": "PREQUEL", "row": _row(3, "Planned show")},
    ]))  # fmt: skip
    nxt = (await client.get("/me/up-next", params={"after": 2})).json()
    assert (nxt["id"], nxt["reason"]) == (62, "related:SEQUEL:Finished show")
    # Without one: the best recommendation not seen yet.
    await redis().delete("related:2")
    nxt = (await client.get("/me/up-next", params={"after": 2})).json()
    assert (nxt["id"], nxt["reason"]) == (60, "Because you liked Y")
    # Nothing recommended: the plan-to-watch list (here by MAL's score).
    with sync_session() as db:
        db.execute(delete(Recommendation))
        db.commit()
    nxt = (await client.get("/me/up-next", params={"after": 2})).json()
    assert nxt["id"] == 4
