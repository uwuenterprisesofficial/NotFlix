from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.models import SourceScan
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
    assert needs_scan(_scan("failed", age=timedelta(minutes=3)), window, ttl)


class CountingProvider:
    """Episodes 1-3 in German, even episodes also in English, nothing after episode 4."""

    name = "counting"

    def __init__(self):
        self.calls: list[int] = []

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
        raise ProviderError("not needed")


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
