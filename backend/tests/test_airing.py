from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.db.session import sync_session
from app.models import AiringEpisode, Anime
from app.services import anilist_account

pytestmark = pytest.mark.anyio

NOW = datetime.now(UTC).replace(microsecond=0)


def _media(mal_id, title, status="RELEASING"):
    return {
        "id": mal_id + 1000, "idMal": mal_id, "episodes": 12, "format": "TV", "status": status,
        "averageScore": 75, "popularity": 1, "duration": 24, "source": "MANGA",
        "title": {"romaji": title, "english": None, "native": None}, "synonyms": [],
        "coverImage": {"large": None}, "description": "", "genres": ["Action"],
        "season": "FALL", "seasonYear": 2026, "startDate": {"year": 2026},
        "studios": {"nodes": []}, "isAdult": False,
    }  # fmt: skip


class FakeAniList:
    schedule: list = []
    next_episode: dict | None = None
    queries: list = []

    def __init__(self, token=None, http=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def query(self, query, variables=None):
        FakeAniList.queries.append(query.split("(")[0].strip())
        if "airingSchedules" in query:
            return {"Page": {"pageInfo": {"hasNextPage": False},
                             "airingSchedules": FakeAniList.schedule}}  # fmt: skip
        return {"Media": {"status": "RELEASING", "nextAiringEpisode": FakeAniList.next_episode}}


@pytest.fixture
def schedule(database, monkeypatch):
    from app.core.cache import redis

    monkeypatch.setattr(anilist_account, "AniListClient", FakeAniList)
    FakeAniList.queries = []
    FakeAniList.next_episode = None
    FakeAniList.schedule = [
        {"episode": 4, "airingAt": int((NOW - timedelta(hours=5)).timestamp()),
         "media": _media(500, "Airing Show")},
        {"episode": 5, "airingAt": int((NOW + timedelta(days=2)).timestamp()),
         "media": _media(500, "Airing Show")},
        {"episode": 1, "airingAt": int((NOW - timedelta(hours=1)).timestamp()),
         "media": _media(501, "Brand New")},
    ]  # fmt: skip
    with sync_session() as db:
        db.execute(delete(AiringEpisode))
        db.execute(delete(Anime).where(Anime.id.in_([500, 501, 502])))
        db.add(Anime(id=500, title="Airing Show (catalogue)", genres=[], num_episodes=12,
                     status="currently_airing"))  # fmt: skip
        db.commit()

    async def clear():
        r = redis()
        keys = [k async for k in r.scan_iter("schedule:*")]
        if keys:
            await r.delete(*keys)

    return clear


async def test_calendar_and_new_episodes(client, schedule, catalogue_jobs):
    await schedule()
    start, end = NOW - timedelta(days=1), NOW + timedelta(days=3)
    body = (
        await client.get("/calendar", params={"start": start.isoformat(), "end": end.isoformat()})
    ).json()
    items = [(a["id"], a["title"], a["airing"]["episode"]) for a in body["items"]]
    assert items == [
        (500, "Airing Show (catalogue)", 4),  # the catalogue's data wins
        (501, "Brand New", 1),  # added to the catalogue from AniList's data
        (500, "Airing Show (catalogue)", 5),
    ]
    assert [501] in [ids for ids, _, _ in catalogue_jobs]  # completed by the worker
    with sync_session() as db:
        show = db.get(Anime, 500)
        assert show.next_episode == 5 and show.next_episode_at > NOW

    # A second look within the hour doesn't ask AniList again.
    count = len(FakeAniList.queries)
    await client.get("/calendar", params={"start": start.isoformat(), "end": end.isoformat()})
    assert len(FakeAniList.queries) == count

    rows = {r["id"]: r for r in (await client.get("/browse")).json()["rows"]}
    new = [(a["id"], a["airing"]["episode"]) for a in rows["new-episodes"]["items"]]
    assert new == [(501, 1), (500, 4)]  # newest first, each show once, nothing upcoming


async def test_calendar_range_is_limited(client, schedule):
    params = {"start": NOW.isoformat(), "end": (NOW + timedelta(days=9)).isoformat()}
    assert (await client.get("/calendar", params=params)).status_code == 422


async def test_unaired_episodes_are_not_looked_for(client, schedule, monkeypatch):
    from app.api import streams
    from app.services import source_scan

    windows = []

    async def ensure_scan(info, window, airing_now, force=False):
        windows.append(window)

    async def no_provider(*args):
        raise AssertionError("providers must not be asked for an unaired episode")

    monkeypatch.setattr(source_scan, "ensure_scan", ensure_scan)
    monkeypatch.setattr(streams, "provider_options", no_provider)
    with sync_session() as db:
        show = db.get(Anime, 500)
        show.next_episode, show.next_episode_at = 5, NOW + timedelta(days=2)
        show.airing_checked_at = NOW
        db.add(Anime(id=502, title="Next Season", genres=[], status="not_yet_aired",
                     airing_checked_at=NOW))  # fmt: skip
        db.commit()

    detail = (await client.get("/anime/500")).json()
    assert (detail["aired_episodes"], detail["next_episode"]) == (4, 5)
    assert (await client.get("/anime/500/episodes/5/sources")).json() == []
    resolve = await client.get("/anime/500/episodes/5/resolve", params={"option": "x:y"})
    assert resolve.status_code == 404 and "hasn't aired" in resolve.json()["detail"]
    await client.get("/anime/500/availability")
    assert windows and max(windows[-1]) == 4  # the scan stops at the last aired episode

    windows.clear()
    await client.get("/anime/502/availability")
    assert windows == []  # nothing has aired: nothing to scan
    assert (await client.get("/anime/502")).json()["aired_episodes"] == 0


async def test_a_passed_air_time_is_checked_again(client, schedule):
    FakeAniList.next_episode = {
        "episode": 7,
        "airingAt": int((NOW + timedelta(days=6)).timestamp()),
    }
    with sync_session() as db:
        show = db.get(Anime, 500)
        show.next_episode, show.next_episode_at = 6, NOW - timedelta(minutes=5)
        show.airing_checked_at = NOW - timedelta(minutes=10)
        db.commit()
    FakeAniList.queries = []
    assert (await client.get("/anime/500")).json()["aired_episodes"] == 6
    assert FakeAniList.queries  # asked, because episode 6's air time had passed
