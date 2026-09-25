import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import update

from app.db.session import sync_session
from app.models import ResolvedSource, SourceScan
from app.providers import base as providers_base
from app.providers.base import ProviderError, Resolved, SourceOption, Stream
from app.services import source_scan
from app.services.source_scan import needs_scan, scan_window

pytestmark = pytest.mark.anyio


def test_scan_window():
    assert scan_window(12, 1) == list(range(1, 13))
    assert scan_window(200, 100) == list(range(95, 155))
    assert scan_window(200, 199) == list(range(141, 201))
    assert scan_window(None, 1) == list(range(1, 25))
    assert scan_window(None, 1100) == list(range(1095, 1113))


def _scan(status, episodes=(), age=timedelta(0)):
    at = datetime.now(UTC) - age
    return SourceScan(status=status, episodes=list(episodes), started_at=at, finished_at=at)


def test_needs_scan():
    window, ttl = [1, 2, 3], timedelta(hours=6)
    assert needs_scan(None, window, ttl)
    assert not needs_scan(_scan("done", [1, 2, 3, 4]), window, ttl)
    assert needs_scan(_scan("done", [1, 2]), window, ttl)  # doesn't cover the window
    assert needs_scan(_scan("done", [1, 2, 3], age=timedelta(hours=7)), window, ttl)
    assert needs_scan(_scan("done", [1, 2, 3]), window, ttl, force=True)
    assert not needs_scan(_scan("running"), window, ttl, force=True)
    assert needs_scan(_scan("running", age=timedelta(minutes=11)), window, ttl)
    assert not needs_scan(_scan("failed", age=timedelta(seconds=30)), window, ttl)
    # Asking to refresh retries a failure right away.
    assert needs_scan(_scan("failed", age=timedelta(seconds=30)), window, ttl, force=True)
    assert needs_scan(_scan("failed", age=timedelta(minutes=3)), window, ttl)


class CountingProvider:
    """Episodes 1-3 in German, even episodes also in English, nothing after episode 4."""

    name = "counting"

    def __init__(self):
        self.calls: list[int] = []
        self.resolves: list[tuple[int, str]] = []

    async def options(self, anime, episode):
        self.calls.append(episode)
        if episode > 4:
            return []
        found = (
            [
                SourceOption(
                    id=f"counting:de{episode}",
                    provider=self.name,
                    label="DE",
                    language="de-dub",
                    resolved=Resolved(streams=[Stream(kind="embed", url="https://e/x", label="E")]),
                )
            ]
            if episode <= 3
            else []
        )
        if episode % 2 == 0:
            found.append(
                SourceOption(
                    id=f"counting:en{episode}", provider=self.name, label="EN", language="en-sub"
                )
            )
        return found

    async def resolve(self, anime, episode, key):
        self.resolves.append((episode, key))
        if not key.startswith("en"):
            raise ProviderError("not needed")
        url = f"https://cdn.example/{episode}.mp4"
        return Resolved(
            streams=[Stream(kind="direct", url=url, label="HD", format="file", relay=True)]
        )


class BrokenProvider(CountingProvider):
    name = "broken"

    async def options(self, anime, episode):
        raise httpx.ConnectError("All connection attempts failed")


@pytest.fixture
def providers(monkeypatch):
    counting, broken = CountingProvider(), BrokenProvider()
    monkeypatch.setattr(providers_base, "enabled_providers", lambda: [counting, broken])
    monkeypatch.setattr(providers_base, "_down_until", {})
    return counting


async def test_detail_page_scan_is_cached_and_reused(client, providers, user):
    first = (await client.get("/anime/9/availability")).json()
    assert first["scanning"] is True
    await source_scan.wait_idle()

    body = (await client.get("/anime/9/availability")).json()
    assert body["scanning"] is False
    assert body["episodes"] == [
        {"episode": 1, "languages": ["de-dub"]},
        {"episode": 2, "languages": ["de-dub", "en-sub"]},
        {"episode": 3, "languages": ["de-dub"]},
        {"episode": 4, "languages": ["en-sub"]},
    ]
    # The unreachable provider doesn't keep episodes from being reported as checked.
    assert body["checked"] == list(range(1, 25))
    scans = {s["provider"]: s for s in body["scans"]}
    assert scans["counting"]["status"] == "done"
    assert scans["broken"]["status"] == "failed"
    assert len(providers.calls) == 24  # unknown episode count: episodes 1-24

    # The player reads the cache: no provider calls.
    sources = (await client.get("/anime/9/episodes/2/sources")).json()
    assert [s["id"] for s in sources] == ["counting:de2", "counting:en2"]
    assert sources[0]["resolved"]["streams"][0]["kind"] == "embed"
    assert len(providers.calls) == 24

    # Refreshing rescans (the broken provider only after its retry delay).
    await client.post("/anime/9/availability/refresh")
    await source_scan.wait_idle()
    assert len(providers.calls) == 48


async def test_player_before_scan_uses_live_lookup_and_caches_it(client, providers, monkeypatch):
    async def no_scan(*args, **kwargs):
        return None

    monkeypatch.setattr(source_scan, "ensure_scan", no_scan)
    first = (
        await client.get("/anime/9/episodes/2/sources", params={"provider": "counting"})
    ).json()
    assert [s["id"] for s in first] == ["counting:de2", "counting:en2"]
    again = (
        await client.get("/anime/9/episodes/2/sources", params={"provider": "counting"})
    ).json()
    assert again == first
    assert providers.calls == [2]
    # A failing provider is not cached as "no sources".
    assert (
        await client.get("/anime/9/episodes/2/sources", params={"provider": "broken"})
    ).json() == []
    assert await source_scan.cached_options(9, 2, "broken") is None


async def test_correcting_the_aniworld_mapping_drops_its_cache(client, user):
    await source_scan.store_episode(9, "aniworld", 1, [])
    assert await source_scan.cached_options(9, 1, "aniworld") == []
    body = {"slug": "one-piece", "season": 1}
    assert (await client.put("/anime/9/mappings/aniworld", json=body)).status_code == 204
    assert await source_scan.cached_options(9, 1, "aniworld") is None


async def test_show_streams_come_in_one_response_with_stored_resolutions(client, providers):
    await client.get("/anime/9/streams", params={"episode": 2})  # starts the scan
    await source_scan.wait_idle()

    body = (await client.get("/anime/9/streams", params={"episode": 2})).json()
    assert body["scanning"] is False
    coverage = {p["name"]: p for p in body["providers"]}
    assert coverage["counting"] == {
        "name": "counting",
        "status": "done",
        "episodes": list(range(1, 25)),
    }
    assert coverage["broken"]["status"] == "failed"
    assert {e["episode"]: [o["id"] for o in e["options"]] for e in body["episodes"]} == {
        1: ["counting:de1"],
        2: ["counting:de2", "counting:en2"],
        3: ["counting:de3"],
        4: ["counting:en4"],
    }
    assert body["resolutions"] == []
    # Unknown show, so treated as airing: the cache is good for the 6 hours until the next scan.
    left = datetime.fromisoformat(body["expires_at"]) - datetime.now(UTC)
    assert timedelta(hours=5, minutes=59) < left <= timedelta(hours=6)

    params = {"option": "counting:en2"}
    resolved = (await client.get("/anime/9/episodes/2/resolve", params=params)).json()
    left = datetime.fromisoformat(resolved["expires_at"]) - datetime.now(UTC)
    assert timedelta(hours=2, minutes=59) < left <= timedelta(hours=3)  # direct links expire
    # Stored: asking again (or after a restart) doesn't ask the provider...
    again = (await client.get("/anime/9/episodes/2/resolve", params=params)).json()
    assert again["resolved_at"] == resolved["resolved_at"]
    assert again["streams"][0]["url"].startswith("/api/proxy?t=")
    assert providers.resolves == [(2, "en2")]
    # ...unless the stored links stopped working.
    await client.get("/anime/9/episodes/2/resolve", params={**params, "fresh": True})
    assert providers.resolves == [(2, "en2"), (2, "en2")]

    body = (await client.get("/anime/9/streams", params={"episode": 2})).json()
    [stored] = body["resolutions"]
    assert (stored["episode"], stored["option"]) == (2, "counting:en2")
    assert stored["resolved"]["streams"][0]["url"].startswith("/api/proxy?t=")

    # Expired resolutions are dropped; a corrected mapping drops the provider's ones too.
    await client.get("/anime/9/episodes/4/resolve", params={"option": "counting:en4"})
    with sync_session() as db:
        db.execute(
            update(ResolvedSource)
            .where(ResolvedSource.episode == 4)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.commit()
    assert [(r.episode, r.option_id) for r in await source_scan.cached_resolutions(9)] == [
        (2, "counting:en2")
    ]
    await source_scan.forget(9, "counting")
    assert await source_scan.cached_resolutions(9) == []


class GatedProvider(CountingProvider):
    """Episodes after 6 wait for the gate: a scan that's partway through."""

    def __init__(self):
        super().__init__()
        self.gate = asyncio.Event()

    async def options(self, anime, episode):
        if episode > 6:
            await self.gate.wait()
        return await super().options(anime, episode)


@pytest.fixture
def gated(monkeypatch):
    provider = GatedProvider()
    monkeypatch.setattr(providers_base, "enabled_providers", lambda: [provider])
    monkeypatch.setattr(providers_base, "_down_until", {})
    yield provider
    provider.gate.set()  # never leave a scan hanging


async def test_scan_results_are_stored_as_they_come(client, gated):
    first = (await client.get("/anime/9/streams", params={"episode": 1})).json()
    assert first["scanning"] is True and first["partial"] is False

    for _ in range(100):  # the first episodes are stored while the rest is still going
        body = (await client.get("/anime/9/availability")).json()
        if len(body["checked"]) >= 6:
            break
        await asyncio.sleep(0.02)
    assert body["scanning"] is True
    assert body["checked"] == [1, 2, 3, 4, 5, 6]
    assert body["progress"] == {"stored": 6, "total": 24}
    assert body["episodes"][1] == {"episode": 2, "languages": ["de-dub", "en-sub"]}
    # The nearest episodes were asked for first.
    assert gated.calls[:6] == [1, 2, 3, 4, 5, 6]

    # The player asks for what changed since its copy: just those episodes, empty ones too.
    delta = (
        await client.get("/anime/9/streams", params={"episode": 1, "after": first["cursor"]})
    ).json()
    assert delta["partial"] is True and delta["resolutions"] == []
    assert [e["episode"] for e in delta["episodes"]] == [1, 2, 3, 4, 5, 6]
    assert delta["episodes"][4] == {"episode": 5, "options": []}
    assert delta["providers"][0]["episodes"] == [1, 2, 3, 4, 5, 6]

    # A stored episode answers right away, though the scan isn't done.
    sources = (await client.get("/anime/9/episodes/2/sources")).json()
    assert [s["id"] for s in sources] == ["counting:de2", "counting:en2"]

    gated.gate.set()
    await source_scan.wait_idle()
    rest = (
        await client.get("/anime/9/streams", params={"episode": 1, "after": delta["cursor"]})
    ).json()
    assert rest["scanning"] is False and rest["progress"] is None
    assert [e["episode"] for e in rest["episodes"]] == list(range(7, 25))


async def test_a_later_scan_only_asks_for_missing_episodes(client, providers):
    await client.get("/anime/9/availability")  # episodes 1-24 (the count is unknown)
    await source_scan.wait_idle()
    providers.calls.clear()
    await client.get("/anime/9/streams", params={"episode": 20})  # episodes 15-32
    await source_scan.wait_idle()
    assert sorted(providers.calls) == list(range(25, 33))


class ListingProvider(CountingProvider):
    """Lists a whole show in one request."""

    name = "listing"
    lists_whole_show = True

    def __init__(self):
        super().__init__()
        self.scans: list[list[int]] = []

    async def scan(self, anime, episodes, found=None):
        self.scans.append(episodes)
        return {ep: [] for ep in episodes}


async def test_listing_providers_cover_the_whole_show(client, monkeypatch, database):
    from app.models import Anime

    with sync_session() as db:
        db.merge(Anime(id=77, title="Long", genres=[], num_episodes=200, status="finished_airing"))
        db.commit()
    counting, listing = CountingProvider(), ListingProvider()
    monkeypatch.setattr(providers_base, "enabled_providers", lambda: [counting, listing])
    await client.get("/anime/77/streams", params={"episode": 100})
    await source_scan.wait_idle()
    # Episode by episode: a window around the user, nearest first.
    assert counting.calls[:3] == [100, 101, 99] and len(counting.calls) == 60
    # One listing: every episode.
    [asked] = listing.scans
    assert sorted(asked) == list(range(1, 201)) and asked[0] == 100


async def test_stream_failures_are_remembered(client, providers):
    from app.models import StreamFailure

    with sync_session() as db:
        db.query(StreamFailure).delete()
        db.commit()
    body = {"option": "counting:en2", "stream": "HD"}
    for _ in range(2):
        res = await client.post("/anime/9/episodes/2/failures", json=body)
        assert res.status_code == 204
    shown = (await client.get("/anime/9/streams", params={"episode": 2})).json()["failures"]
    assert [(f["episode"], f["option"], f["stream"], f["count"]) for f in shown] == [
        (2, "counting:en2", "HD", 2)
    ]
    # Also in the changes-only answer.
    cursor = (await client.get("/anime/9/streams")).json()["cursor"]
    delta = (await client.get("/anime/9/streams", params={"after": cursor})).json()
    assert len(delta["failures"]) == 1
    # It played after all.
    await client.delete("/anime/9/episodes/2/failures", params=body)
    assert (await client.get("/anime/9/streams")).json()["failures"] == []
