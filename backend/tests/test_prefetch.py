import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from app.db.session import sync_session
from app.models import Anime, SourceScan
from app.providers import base as providers_base
from app.providers.base import Resolved, SourceOption, Stream
from app.services import prefetch, source_scan

pytestmark = pytest.mark.anyio

SHOWS = (41, 42, 43)


class SlowProvider:
    """One option per episode, each lookup taking a moment; resolves to a direct stream."""

    name = "slow"
    delay = 0.05

    def __init__(self):
        self.calls: list[tuple[int, int]] = []
        self.delays: dict[int, float] = {}  # per show

    async def options(self, anime, episode):
        self.calls.append((anime.id, episode))
        await asyncio.sleep(self.delays.get(anime.id, self.delay))
        return [
            SourceOption(id=f"slow:{episode}", provider=self.name, label="S", language="de-sub")
        ]

    async def resolve(self, anime, episode, key):
        url = f"https://cdn.example/{anime.id}/{episode}.mp4"
        return Resolved(streams=[Stream(kind="direct", url=url, label="HD", format="file")])

    def episodes_of(self, anime_id):
        return [ep for a, ep in self.calls if a == anime_id]


@pytest.fixture
def slow(database, monkeypatch):
    provider = SlowProvider()
    monkeypatch.setattr(providers_base, "enabled_providers", lambda: [provider])
    monkeypatch.setattr(providers_base, "_down_until", {})
    monkeypatch.setattr(source_scan, "BACKGROUND_POLL_S", 0.02)
    monkeypatch.setattr(prefetch, "WAIT_POLL_S", 0.02)
    # One worker: anything someone waits for takes it.
    monkeypatch.setattr(source_scan, "SCAN_WORKERS", 1)
    prefetch.clear()
    with sync_session() as db:
        db.execute(delete(Anime).where(Anime.id.in_(SHOWS)))
        for anime_id in SHOWS:
            db.add(Anime(id=anime_id, title=f"Show {anime_id}", genres=[], num_episodes=6,
                         status="finished_airing", mal_details_at=datetime.now(UTC),
                         enriched_at=datetime.now(UTC)))  # fmt: skip
        db.commit()
    from redis import Redis

    from app.core.config import get_settings

    r = Redis.from_url(get_settings().redis_url)
    for key in [*r.scan_iter("prefetch:done:*"), *r.scan_iter("preview:miss:*")]:
        r.delete(key)
    yield provider
    prefetch.clear()


async def _until(condition, timeout=5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        assert asyncio.get_running_loop().time() < deadline, "timed out"
        await asyncio.sleep(0.02)


async def test_shows_on_the_pages_are_scanned_by_free_workers(client, slow):
    resp = await client.post(
        "/prefetch", json={"shows": [{"id": 41, "episode": 1}, {"id": 42, "episode": 3}]}
    )
    assert resp.json() == {"queued": 2}
    await prefetch.wait_idle()
    await source_scan.wait_idle()
    # One show after the other, in the page's order, every (short) show's episodes.
    assert slow.episodes_of(41) and slow.episodes_of(42)
    assert max(i for i, (a, _) in enumerate(slow.calls) if a == 41) < min(
        i for i, (a, _) in enumerate(slow.calls) if a == 42
    )
    assert sorted(slow.episodes_of(42)) == [1, 2, 3, 4, 5, 6]
    # Done shows aren't looked at again; neither are ones a provider has looked at already.
    slow.calls.clear()
    with sync_session() as db:
        now = datetime.now(UTC)
        db.add(SourceScan(anime_id=43, provider="slow", status="done", episodes=[1],
                          started_at=now, finished_at=now))  # fmt: skip
        db.commit()
    await client.post("/prefetch", json={"shows": [{"id": 41}, {"id": 43}]})
    await prefetch.wait_idle()
    await source_scan.wait_idle()
    assert slow.calls == []


async def test_background_scans_hold_while_someone_waits_for_every_worker(client, slow):
    slow.delay = 0.1
    slow.delays[42] = 0.6  # the show someone opens takes a while
    await client.post("/prefetch", json={"shows": [{"id": 41}]})
    # A free worker: it starts right away.
    await _until(lambda: len(slow.calls) >= 1)
    # Someone opens another show: its scan takes the (only) worker, the background one holds.
    await client.get("/anime/42/availability")
    await asyncio.sleep(0.15)
    held = len(slow.episodes_of(41))
    await asyncio.sleep(0.2)
    assert len(slow.episodes_of(41)) == held < 6
    assert len(slow.episodes_of(42)) > 1
    # Once that's done, it carries on.
    await _until(lambda: len(slow.episodes_of(41)) == 6)
    await source_scan.wait_idle()


async def test_free_workers_take_several_shows_at_once(client, slow, monkeypatch):
    monkeypatch.setattr(source_scan, "SCAN_WORKERS", 2)
    slow.delay = 0.1
    await client.post("/prefetch", json={"shows": [{"id": 41}, {"id": 42}, {"id": 43}]})
    await _until(lambda: slow.episodes_of(41) and slow.episodes_of(42))
    assert not slow.episodes_of(43)  # two workers: the third show waits its turn
    await prefetch.wait_idle()
    await source_scan.wait_idle()
    assert len(slow.episodes_of(43)) == 6


async def test_opening_a_show_promotes_its_background_scan(client, slow):
    slow.delay = 0.1
    await client.post("/prefetch", json={"shows": [{"id": 41}]})
    await _until(lambda: len(slow.calls) >= 1)
    # Opening the show: its own scan now runs at full speed, whatever else needs workers.
    body = (await client.get("/anime/41/availability")).json()
    assert body["scanning"] is True
    await client.get("/anime/42/availability")  # and something else needs the worker
    await _until(lambda: len(slow.episodes_of(41)) == 6, timeout=2)
    await source_scan.wait_idle()
    scans = await source_scan.provider_scans(41)
    assert scans["slow"].episodes == [1, 2, 3, 4, 5, 6]


async def test_lingering_on_a_card_scans_for_its_preview(client, slow):
    # Hovering alone doesn't scan.
    assert (await client.get("/anime/43/preview")).status_code == 404
    assert slow.calls == []
    # Lingering does: episode 1 only, right away, and the preview plays.
    resp = await client.get("/anime/43/preview", params={"scan": "true"})
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://cdn.example/43/1.mp4"
    assert slow.episodes_of(43) == [1]
    await source_scan.wait_idle()
