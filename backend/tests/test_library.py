import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.core.cache import redis
from app.db.session import sync_session
from app.models import Anime, ListEntry

pytestmark = pytest.mark.anyio


def _row(mal_id: int, title: str, media_type: str = "tv") -> dict:
    return {"id": mal_id, "title": title, "media_type": media_type, "genres": []}


@pytest.fixture
def listed(user):
    now = datetime.now(UTC)
    with sync_session() as db:
        db.execute(delete(ListEntry))
        db.execute(delete(Anime))
        db.add_all([
            Anime(id=1, title="Airing show", genres=[], status="currently_airing"),
            Anime(id=2, title="Finished show", genres=[], status="finished_airing"),
            Anime(id=3, title="Planned show", genres=[], status="finished_airing"),
            Anime(id=4, title="Planned and airing", genres=[], status="currently_airing"),
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
        {"relation": "SIDE_STORY", "row": _row(50, "The Film", "movie")},
        {"relation": "SEQUEL", "row": _row(51, "Season 2")},
        {"relation": "PREQUEL", "row": _row(3, "Planned show")},
        {"relation": "SEQUEL", "row": _row(1, "Airing show")},
    ]))  # fmt: skip
    await redis().delete("related:1")

    body = (await client.get("/me/library")).json()
    sections = {s["id"]: [a["id"] for a in s["items"]] for s in body["sections"]}
    assert sections == {"continue": [1], "season": [1, 4], "planned": [3, 4], "related": [50, 51]}
    related_cards = next(s for s in body["sections"] if s["id"] == "related")["items"]
    assert related_cards[0]["reason"] == "related:SIDE_STORY:Finished show"
    assert related_cards[0]["media_type"] == "movie"
    # The airing show's relations weren't cached: fetched in the background.
    assert body["related_pending"] is True or fetched == [[1]]
    await related.wait_idle()
    assert fetched == [[1]]
    await redis().delete("related:2")


async def _none():
    return None
