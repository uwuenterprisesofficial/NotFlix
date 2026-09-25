import httpx
import pytest
from sqlalchemy import delete

from app.db.session import sync_session
from app.models import AnalysisJob, Anime, EpisodeFingerprint, ReferenceSegment, SkipSegment
from app.services import aniskip

pytestmark = pytest.mark.anyio

RESULT = {
    "found": True,
    "results": [
        {"interval": {"startTime": 88.5, "endTime": 178.6}, "skipType": "op"},
        {"interval": {"startTime": 1310.0, "endTime": 1400.0}, "skipType": "ed"},
    ],
}


@pytest.fixture
def fake_aniskip(database, monkeypatch):
    from redis import Redis

    from app.core.config import get_settings

    r = Redis.from_url(get_settings().redis_url)
    for key in [*r.scan_iter("aniskip:*"), *r.scan_iter("analysis:retry:*")]:
        r.delete(key)
    with sync_session() as db:
        for model in (SkipSegment, EpisodeFingerprint, ReferenceSegment, AnalysisJob):
            db.execute(delete(model))
        db.merge(Anime(id=5, title="Five", genres=[], num_episodes=12))
        db.commit()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/5/1"):
            return httpx.Response(200, json=RESULT)
        return httpx.Response(404, json={"found": False, "results": []})

    monkeypatch.setattr(get_settings(), "aniskip_url", "https://aniskip.test")
    monkeypatch.setattr(aniskip, "_transport", httpx.MockTransport(handler))
    return calls


async def test_aniskip_fills_in_until_the_detection_has_times(client, fake_aniskip):
    body = (await client.get("/anime/5/episodes/1")).json()
    got = {(s["kind"], s["start_s"], s["source"]) for s in body["skip_segments"]}
    assert got == {("opening", 88.5, "aniskip"), ("ending", 1310.0, "aniskip")}
    await client.get("/anime/5/episodes/1")
    assert len(fake_aniskip) == 1  # stored: not asked again

    # A miss isn't asked again for a day either.
    for _ in range(2):
        assert (await client.get("/anime/5/episodes/2")).json()["skip_segments"] == []
    assert len(fake_aniskip) == 2

    # A detected opening wins: AniSkip isn't asked for an episode that has one.
    with sync_session() as db:
        db.add(SkipSegment(anime_id=5, episode=3, kind="opening", start_s=80, end_s=170,
                           confidence=0.9, source="analysis"))  # fmt: skip
        db.commit()
    assert (await client.get("/anime/5/episodes/3")).json()["skip_segments"][0]["start_s"] == 80
    assert len(fake_aniskip) == 2


async def test_auto_analysis_retries_episodes_without_an_opening(
    client, user, fake_aniskip, monkeypatch
):
    queued = []

    class FakeQueue:
        def enqueue(self, func, *args, **kwargs):
            queued.append(args)

    monkeypatch.setattr("app.api.anime.analysis_queue", lambda: FakeQueue())
    fp = {"language": "de-dub", "hashes": b"", "valid": b"", "frames": 0, "hop_seconds": 0.1}
    await client.get("/anime/5/episodes/1")  # AniSkip's times for episode 1
    with sync_session() as db:
        # Episodes 1 and 2 were analysed; nothing was found.
        db.add(EpisodeFingerprint(anime_id=5, episode=1, compared_with=[2], **fp))
        db.add(EpisodeFingerprint(anime_id=5, episode=2, compared_with=[1], **fp))
        db.commit()

    async def auto():
        body = {"episode": 1, "language": "de-dub"}
        return (await client.post("/anime/5/analyze/auto", json=body)).json()

    # No opening fingerprint to search for: nothing new to try.
    assert (await auto())["job"] is None
    with sync_session() as db:
        db.add(ReferenceSegment(anime_id=5, kind="opening", source_episode=3, hashes=b"",
                                valid=b"", frames=0, hop_seconds=0.1))  # fmt: skip
        db.commit()
    # Now there is one (e.g. learned from other episodes): both are tried again, once a day.
    assert (await auto())["job"]["episodes"] == [1, 2]
    with sync_session() as db:
        db.execute(delete(AnalysisJob))
        db.commit()
    assert (await auto())["job"] is None
