from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.db.session import sync_session
from app.models import Anime, AnimeSynopsis
from app.services import catalog_jobs, mal

pytestmark = pytest.mark.anyio

NOW = datetime.now(UTC)


def _node(anime_id, title, **extra):
    return {
        "id": anime_id, "title": title, "genres": [{"id": 1, "name": "Action"}],
        "alternative_titles": {"synonyms": [f"{title} alt"], "en": None, "ja": "日本語"},
        "mean": 8.0, "num_list_users": 1000, **extra,
    }  # fmt: skip


@pytest.fixture
def catalogue(database, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "mal_client_id", "cid")
    with sync_session() as db:
        db.execute(delete(AnimeSynopsis))
        db.execute(delete(Anime))
        db.add(
            Anime(
                id=21, title="One Piece (catalogue)", genres=["Action"], mean=8.7,
                alt_titles=["Wan Pīsu"], mal_details_at=NOW - timedelta(days=90),
                enriched_at=NOW - timedelta(days=90), popularity=1,
            )
        )  # fmt: skip
        db.commit()


@pytest.fixture
def mal_calls(monkeypatch):
    calls: list[tuple] = []

    async def anime(self, anime_id, extra_fields=""):
        calls.append(("anime", anime_id))
        return _node(anime_id, f"Fetched {anime_id}")

    async def search(self, query, limit=30, offset=0):
        calls.append(("search", query))
        return [_node(21, "One Piece (MAL)"), _node(30, "One Piece Film")]

    monkeypatch.setattr(mal.MalClient, "anime", anime)
    monkeypatch.setattr(mal.MalClient, "search", search)
    return calls


async def test_a_show_in_the_catalogue_is_not_fetched_again(
    client, catalogue, mal_calls, catalogue_jobs
):
    body = (await client.get("/anime/21")).json()
    assert body["title"] == "One Piece (catalogue)"
    assert mal_calls == []
    # Its data is 90 days old: refreshed in the background, not while the page waits.
    assert catalogue_jobs == [([21], [], True)]


async def test_a_new_show_is_fetched_once_and_completed_later(
    client, catalogue, mal_calls, catalogue_jobs
):
    assert (await client.get("/anime/5")).json()["title"] == "Fetched 5"
    assert (await client.get("/anime/5")).json()["title"] == "Fetched 5"
    assert mal_calls == [("anime", 5)]
    assert [ids for ids, _, _ in catalogue_jobs] == [[5]]  # queued once for the synopsis etc.
    with sync_session() as db:
        stored = db.get(Anime, 5)
        assert stored.mal_details_at is not None and stored.alt_titles == [
            "Fetched 5 alt",
            "日本語",
        ]


async def test_search_uses_the_catalogue_and_queues_new_shows(
    client, catalogue, mal_calls, catalogue_jobs, monkeypatch
):
    with sync_session() as db:
        db.add(Anime(id=99, title="Kaizoku", alt_titles=["one piece special"], genres=[]))
        db.commit()
    body = (await client.get("/search", params={"q": "one piece"})).json()
    titles = [a["title"] for a in body["items"]]
    # MAL's order; the catalogue's data for a show it has; a catalogue-only match after.
    assert titles == ["One Piece (catalogue)", "One Piece Film", "Kaizoku"]
    [(ids, rows, _)] = [job for job in catalogue_jobs if job[1]]
    assert ids == [30] and rows[0]["title"] == "One Piece Film"
    with sync_session() as db:
        assert db.get(Anime, 30) is None  # stored by the worker, not by the search

    # The same search again doesn't ask MAL.
    await client.get("/search", params={"q": "One Piece"})
    assert [c for c in mal_calls if c[0] == "search"] == [("search", "one piece")]

    # Without MAL, the catalogue alone answers, alternative titles included.
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "mal_client_id", "")
    body = (await client.get("/search", params={"q": "Pīsu"})).json()
    assert (body["source"], [a["id"] for a in body["items"]]) == ("local", [21])


async def test_queued_once_within_the_hour(client):
    assert await catalog_jobs.enqueue([1, 2]) == [1, 2]
    assert await catalog_jobs.enqueue([2, 3]) == [3]


async def test_worker_stores_and_completes_shows(client, catalogue, mal_calls, monkeypatch):
    # (`client` closes the database/Redis connections this test's event loop opens.)
    from app.providers import base
    from app.worker import catalog as worker

    class GermanSource:
        name = "aniworld"

        async def description(self, anime):
            return f"Deutsch: {anime.title}"

    monkeypatch.setattr(base, "enabled_providers", lambda: [GermanSource()])
    rows = [
        mal.anime_from_node(_node(30, "One Piece Film")),
        {  # from Jikan/AniList: no MAL details yet
            "id": 40, "title": "From elsewhere", "genres": [], "genre_tags": [],
            "alt_titles": [],
        },
    ]  # fmt: skip
    await worker.run([30, 40, 21], rows, refresh=True)

    # MAL is asked only for what it hasn't provided, or is due (21 is 90 days old).
    assert sorted(mal_calls) == [("anime", 21), ("anime", 40)]
    with sync_session() as db:
        assert db.get(Anime, 40).title == "Fetched 40"
        for anime_id in (21, 30, 40):
            assert db.get(Anime, anime_id).enriched_at is not None
        german = {s.anime_id: s.synopsis for s in db.query(AnimeSynopsis)}
    assert german[30] == "Deutsch: One Piece Film"
    assert set(german) == {21, 30, 40}
