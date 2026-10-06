import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete, select
from test_scan import CountingProvider

from app.core.config import get_settings
from app.db.session import sync_session
from app.models import Anime, EpisodeSource, SharedSource, SourceScan
from app.providers import base as providers_base
from app.services import library, source_scan

pytestmark = pytest.mark.anyio

SOURCE = "counting/CountingProvider"


@pytest.fixture
def counting(monkeypatch):
    provider = CountingProvider()
    monkeypatch.setattr(providers_base, "enabled_providers", lambda: [provider])
    monkeypatch.setattr(providers_base, "_down_until", {})
    return provider


def _forget_local_cache(anime_id: int) -> None:
    """As if this server had never scanned the show (the library keeps what it found)."""
    with sync_session() as db:
        db.execute(delete(EpisodeSource).where(EpisodeSource.anime_id == anime_id))
        db.execute(delete(SourceScan).where(SourceScan.anime_id == anime_id))
        db.commit()


async def _allow_pull(anime_id: int) -> None:
    from app.core.cache import redis

    await redis().delete(f"library:pulled:{anime_id}")


async def test_apps_share_sources(client):
    embed = {"streams": [{"kind": "embed", "url": "https://embed.example/1", "label": "E",
                          "format": None, "headers": {}, "subtitles": [], "relay": False}],
             "segments": []}  # fmt: skip
    direct = {**embed, "streams": [{**embed["streams"][0], "kind": "direct"}]}
    body = {
        "anime_id": 5,
        "source": SOURCE,
        "episodes": [
            {"episode": 1, "options": [
                {"id": "counting:a", "label": "A", "language": "de-dub", "resolved": embed},
                {"id": "counting:b", "label": "B", "language": "en-sub", "resolved": direct},
            ]},
            {"episode": 2, "options": []},
        ],
    }  # fmt: skip
    assert (await client.post("/library/sources", json=body)).status_code == 204

    [shared] = (await client.get("/library/sources/5")).json()
    assert shared["source"] == SOURCE
    first, second = shared["episodes"]
    # Embed pages stay put and are shared resolved; direct links expire and aren't.
    assert first["options"] == [
        {"id": "counting:a", "label": "A", "language": "de-dub", "resolved": embed},
        {"id": "counting:b", "label": "B", "language": "en-sub"},
    ]
    assert second == {**second, "episode": 2, "options": []}  # checked, nothing found
    assert (await client.get("/library/sources/6")).json() == []

    # Option ids must be the provider's own; local files aren't shared.
    wrong = {**body, "episodes": [{"episode": 1, "options": [
        {"id": "other:a", "label": "A", "language": "de-dub"}]}]}  # fmt: skip
    assert (await client.post("/library/sources", json=wrong)).status_code == 422
    local = {**body, "source": "database/DatabaseProvider", "episodes": []}
    assert (await client.post("/library/sources", json=local)).status_code == 422
    assert (await client.post("/library/sources", json={**body, "source": "x"})).status_code == 422


async def test_library_requires_the_api_key(client):
    resp = await client.get("/library/sources/5", headers={"x-api-key": "wrong"})
    assert resp.status_code == 401


async def test_what_a_scan_finds_is_reused_instead_of_scanning_again(client, counting):
    await client.get("/anime/9/availability")
    await source_scan.wait_idle()
    with sync_session() as db:
        rows = db.scalars(select(SharedSource).where(SharedSource.anime_id == 9)).all()
    assert {r.source for r in rows} == {SOURCE}
    assert {r.episode for r in rows} == set(range(1, 25))

    before = (await client.get("/anime/9/availability")).json()
    _forget_local_cache(9)
    await _allow_pull(9)
    counting.calls.clear()

    after = (await client.get("/anime/9/availability")).json()
    assert after["scanning"] is False
    assert counting.calls == []
    assert after["episodes"] == before["episodes"]
    assert after["checked"] == list(range(1, 25))
    # The player gets the shared options (embeds resolved, as found).
    sources = (await client.get("/anime/9/episodes/2/sources")).json()
    assert [(o["id"], o["resolved"] is not None) for o in sources] == [
        ("counting:de2", True),
        ("counting:en2", False),
    ]
    assert counting.calls == []


async def test_a_newer_own_scan_only_takes_missing_episodes(client, counting, monkeypatch):
    now = datetime.now(UTC)
    with sync_session() as db:
        db.add(SourceScan(anime_id=12, provider="counting", status="done", episodes=[1],
                          started_at=now, finished_at=now))  # fmt: skip
        db.add(EpisodeSource(anime_id=12, episode=1, provider="counting", option_id="counting:own",
                             label="Own", language="de-sub", position=0))  # fmt: skip
        db.commit()
    older = now - timedelta(hours=1)
    shared = {
        SOURCE: {
            1: ([{"id": "counting:old", "label": "Old", "language": "de-dub"}], older),
            2: ([{"id": "counting:two", "label": "Two", "language": "de-dub"}], older),
        },
        "elsewhere/OtherProvider": {1: ([], older)},  # a provider this server doesn't have
    }

    async def fake_shared(anime_id):
        return shared

    monkeypatch.setattr(library, "shared", fake_shared)
    await library.pull(12)

    scans = await source_scan.provider_scans(12)
    assert scans["counting"].episodes == [1, 2]
    assert scans["counting"].finished_at == now  # still this server's own scan
    _, options = await source_scan.cached_sources(12, ["counting"])
    assert [o.id for o in options[1]] == ["counting:own"]
    assert [o.id for o in options[2]] == ["counting:two"]

    # Asked again within PULL_EVERY_S: nothing happens.
    shared[SOURCE][3] = ([], now)
    await library.pull(12)
    assert (await source_scan.provider_scans(12))["counting"].episodes == [1, 2]


@pytest.fixture
def upstream(monkeypatch):
    """This server in hybrid mode, with a fake online server."""
    settings = get_settings()
    monkeypatch.setattr(settings, "upstream_url", "https://online.example/api/")
    monkeypatch.setattr(settings, "upstream_api_key", "online-key-0123456789")
    seen: list[httpx.Request] = []
    pushed: list[dict] = []
    shared: dict[int, list[dict]] = {}
    old = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path.removeprefix("/api")
        if path == "/library/anime/77":
            return httpx.Response(200, json={
                "id": 77, "title": "Upstream Show", "title_en": "Upstream", "num_episodes": 3,
                "status": "finished_airing", "genres": ["Action"], "alt_titles": [],
                "mal_details_at": "2026-10-01T12:00:00+00:00", "media_type": "tv",
            })  # fmt: skip
        if path.startswith("/library/anime/"):
            return httpx.Response(404, json={"detail": "Unknown anime"})
        if path.startswith("/library/sources/"):
            anime_id = int(path.rsplit("/", 1)[1])
            return httpx.Response(200, json=shared.get(anime_id, []))
        if path == "/library/sources" and request.method == "POST":
            pushed.append(json.loads(request.content))
            return httpx.Response(204)
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(library, "_client", lambda: client)
    shared[77] = [{
        "source": SOURCE,
        "episodes": [
            {"episode": ep, "options": [
                {"id": f"counting:de{ep}", "label": "DE", "language": "de-dub"}],
             "updated_at": old}
            for ep in (1, 2, 3)
        ],
    }]  # fmt: skip
    return seen, pushed


async def test_refreshing_needs_a_user_unless_users_sign_in_upstream(client, counting):
    assert (await client.post("/anime/9/availability/refresh")).status_code == 401


async def test_hybrid_mode_uses_the_online_servers_catalogue_and_library(
    client, counting, upstream
):
    seen, pushed = upstream
    with sync_session() as db:
        db.execute(delete(Anime).where(Anime.id.in_([77, 78])))
        db.commit()

    body = (await client.get("/anime/77/availability")).json()
    await source_scan.wait_idle()
    # The show came from the online server, with its key.
    with sync_session() as db:
        anime = db.get(Anime, 77)
        assert (anime.title, anime.num_episodes, anime.genres) == ("Upstream Show", 3, ["Action"])
        assert anime.mal_details_at == datetime(2026, 10, 1, 12, tzinfo=UTC)
    assert all(r.headers["x-api-key"] == "online-key-0123456789" for r in seen)
    # Its library covered every episode: nothing was looked for here.
    assert body["scanning"] is False
    assert counting.calls == []
    assert [e["episode"] for e in body["episodes"]] == [1, 2, 3]
    assert pushed == []  # what came from the library isn't sent back

    # A refresh looks itself, and shares what it found. (Users sign in on the online server:
    # this one has none.)
    assert (await client.post("/anime/77/availability/refresh?episode=2")).status_code == 200
    await source_scan.wait_idle()
    await library.wait_idle()
    assert sorted(counting.calls) == [1, 2, 3]
    sent = {e["episode"]: e["options"] for p in pushed for e in p["episodes"]}
    assert {p["source"] for p in pushed} == {SOURCE}
    assert sent[2] == [
        {"id": "counting:de2", "label": "DE", "language": "de-dub",
         "resolved": sent[2][0]["resolved"]},
        {"id": "counting:en2", "label": "EN", "language": "en-sub"},
    ]  # fmt: skip
    assert sent[2][0]["resolved"]["streams"][0]["kind"] == "embed"

    # A show the online server doesn't know isn't asked for again right away.
    before = len(seen)
    await client.get("/anime/78/availability")
    await client.get("/anime/78/availability")
    await source_scan.wait_idle()
    anime_requests = [r for r in seen[before:] if "/library/anime/" in r.url.path]
    assert len(anime_requests) == 1


async def test_a_broken_upstream_never_breaks_looking_for_streams(client, counting, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "upstream_url", "https://online.example")

    def broken():
        raise PermissionError("can't read the CA bundle")

    monkeypatch.setattr(library, "_client", broken)
    resp = await client.get("/anime/79/availability")
    await source_scan.wait_idle()
    await library.wait_idle()
    assert resp.status_code == 200
    assert counting.calls  # looked for itself
