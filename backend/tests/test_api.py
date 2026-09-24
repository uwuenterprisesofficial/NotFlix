import numpy as np
import pytest
from sqlalchemy import delete, select

from app.db.session import sync_session
from app.models import AnalysisJob, JobStatus, SkipSegment, StreamSource

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def clean_tables(database):
    with sync_session() as db:
        for model in (AnalysisJob, SkipSegment, StreamSource):
            db.execute(delete(model))
        db.commit()


async def test_health(client):
    resp = await client.get("/health")
    assert resp.json() == {"status": "ok"}


async def test_browse_anonymous_without_mal_credentials(client):
    resp = await client.get("/browse")
    assert resp.status_code == 200
    assert resp.json() == {"hero": None, "rows": [], "signed_in": False, "mal_configured": False}


async def test_login_requires_mal_client_id(client):
    resp = await client.get("/auth/login")
    assert resp.status_code == 503


async def test_episode_returns_skip_segments(client):
    with sync_session() as db:
        db.add(
            SkipSegment(
                anime_id=5, episode=1, kind="opening", start_s=30, end_s=120, confidence=0.9
            )
        )
        db.commit()

    body = (await client.get("/anime/5/episodes/1")).json()
    assert body["skip_segments"][0]["kind"] == "opening"
    assert body["skip_segments"][0]["end_s"] == 120


async def test_sources_include_stored_stream_sources(client):
    with sync_session() as db:
        db.add(
            StreamSource(
                anime_id=5,
                episode=1,
                provider="p",
                kind="embed",
                url="https://x/e/1",
                language="de-sub",
            )
        )
        db.commit()

    [option] = (await client.get("/anime/5/episodes/1/sources")).json()
    assert option["provider"] == "database"
    assert option["language"] == "de-sub"
    assert option["resolved"]["streams"] == [
        {"kind": "embed", "url": "https://x/e/1", "label": "p", "format": None, "subtitles": []}
    ]
    resolved = (
        await client.get("/anime/5/episodes/1/resolve", params={"option": option["id"]})
    ).json()
    assert resolved["streams"][0]["url"] == "https://x/e/1"
    missing = await client.get("/anime/5/episodes/2/resolve", params={"option": option["id"]})
    assert missing.status_code == 404


async def test_analyze_requires_sign_in(client):
    resp = await client.post("/anime/5/analyze", json={"episodes": [1, 2]})
    assert resp.status_code == 401


async def test_analyze_validates_episodes(client, user):
    resp = await client.post("/anime/5/analyze", json={"episodes": [3, 3]})
    assert resp.status_code == 422


async def test_analyze_queues_job_and_reuses_finished_episodes(client, user, monkeypatch):
    queued = []

    class FakeQueue:
        def enqueue(self, func, *args, **kwargs):
            queued.append(args)

    monkeypatch.setattr("app.api.anime.analysis_queue", lambda: FakeQueue())

    body = (await client.post("/anime/5/analyze", json={"episodes": [2, 1]})).json()
    assert body["cached"] is False
    assert body["job"]["episodes"] == [1, 2]
    assert queued == [(body["job"]["id"],)]

    with sync_session() as db:
        db.get(AnalysisJob, body["job"]["id"]).status = JobStatus.done
        db.commit()

    cached = (await client.post("/anime/5/analyze", json={"episodes": [1, 2]})).json()
    assert cached == {"cached": True, "job": None}

    # Only episode 3 is new; episode 1 is reused as the comparison reference.
    body = (await client.post("/anime/5/analyze", json={"episodes": [1, 2, 3]})).json()
    assert body["job"]["episodes"] == [1, 3]


def test_worker_stores_detected_segments(database, monkeypatch):
    from app.analysis.audio import SAMPLE_RATE
    from app.analysis.media import Media
    from app.worker.tasks import run_analysis

    rng = np.random.default_rng(1)
    opening = rng.standard_normal(80 * SAMPLE_RATE).astype(np.float32)
    ending = rng.standard_normal(80 * SAMPLE_RATE).astype(np.float32)

    def fake_episode(intro_at: int) -> np.ndarray:
        pad = lambda s: rng.standard_normal(s * SAMPLE_RATE).astype(np.float32)  # noqa: E731
        return np.concatenate([pad(intro_at), opening, pad(600), ending, pad(30)])

    audio = {"ep1": fake_episode(10), "ep2": fake_episode(70)}
    monkeypatch.setattr(
        "app.worker.tasks.resolve_all",
        lambda anime_id, episodes: {ep: Media(f"ep{ep}") for ep in episodes},
    )
    monkeypatch.setattr("app.worker.tasks.load_audio", lambda source, headers: audio[source])

    with sync_session() as db:
        db.add(AnalysisJob(id="job-1", anime_id=7, episodes=[1, 2]))
        db.add(
            SkipSegment(
                anime_id=7,
                episode=2,
                kind="ending",
                start_s=1,
                end_s=2,
                confidence=1,
                source="manual",
            )
        )
        db.commit()

    run_analysis("job-1")

    with sync_session() as db:
        assert db.get(AnalysisJob, "job-1").status == JobStatus.done
        rows = {
            (s.episode, s.kind): s
            for s in db.scalars(select(SkipSegment).where(SkipSegment.anime_id == 7))
        }
    assert rows[(1, "opening")].start_s == pytest.approx(10, abs=1.5)
    assert rows[(2, "opening")].start_s == pytest.approx(70, abs=1.5)
    assert rows[(1, "ending")].start_s == pytest.approx(690, abs=1.5)
    assert rows[(2, "ending")].source == "manual"
    assert rows[(2, "ending")].start_s == 1


def test_worker_marks_job_failed_when_media_missing(database):
    from app.worker.tasks import run_analysis

    with sync_session() as db:
        db.add(AnalysisJob(id="job-2", anime_id=8, episodes=[1, 2]))
        db.commit()

    run_analysis("job-2")

    with sync_session() as db:
        job = db.get(AnalysisJob, "job-2")
        assert job.status == JobStatus.failed
        assert "No media for anime 8 episode 1" in job.error
        assert job.finished_at is not None
