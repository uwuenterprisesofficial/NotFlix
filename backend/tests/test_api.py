import numpy as np
import pytest
from sqlalchemy import delete, select, update

from app.db.session import sync_session
from app.models import (
    AnalysisJob,
    Anime,
    EpisodeFingerprint,
    JobStatus,
    ReferenceSegment,
    SkipSegment,
    StreamSource,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def clean_tables(database):
    with sync_session() as db:
        for model in (AnalysisJob, SkipSegment, StreamSource, EpisodeFingerprint, ReferenceSegment):
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
    assert (await client.post("/anime/5/analyze", json={"episodes": [0, 1]})).status_code == 422
    # One episode (here the same one twice) needs a saved fingerprint to match it against.
    resp = await client.post("/anime/5/analyze", json={"episodes": [3, 3]})
    assert resp.status_code == 422
    assert "Pick two episodes" in resp.json()["detail"]


async def test_manual_analysis_always_recalculates(client, user, monkeypatch):
    queued = []

    class FakeQueue:
        def enqueue(self, func, *args, **kwargs):
            queued.append(args)

    monkeypatch.setattr("app.api.anime.analysis_queue", lambda: FakeQueue())

    async def analyze(**body):
        return (await client.post("/anime/5/analyze", json=body)).json()

    body = await analyze(episodes=[2, 1], language="de-sub")
    assert body["cached"] is False
    job = body["job"]
    assert (job["episodes"], job["language"], job["compare"], job["redownload"]) == (
        [1, 2], "de-sub", False, False,
    )  # fmt: skip
    assert queued == [(job["id"],)]

    with sync_session() as db:
        db.get(AnalysisJob, job["id"]).status = JobStatus.done
        db.add(
            ReferenceSegment(
                anime_id=5, kind="opening", source_episode=1, hashes=b"", valid=b"", frames=0,
                hop_seconds=0.1,
            )
        )  # fmt: skip
        db.commit()

    # Analysed episodes are analysed again when asked (their results are replaced)...
    assert (await analyze(episodes=[1, 2]))["job"]["episodes"] == [1, 2]
    # ...and with a saved fingerprint, one episode is enough, e.g. to retry it.
    retry = (await analyze(episodes=[2], redownload=True))["job"]
    assert (retry["episodes"], retry["redownload"]) == ([2], True)
    assert len(queued) == 3

    overview = (await client.get("/anime/5/analysis")).json()
    [reference] = overview["references"]
    assert (reference["kind"], reference["source_episode"]) == ("opening", 1)
    url = f"/anime/5/analysis/references/{reference['id']}"
    assert (await client.delete(url)).status_code == 204
    assert (await client.delete(url)).status_code == 404
    assert (await client.get("/anime/5/analysis")).json()["references"] == []


def test_worker_learns_the_opening_and_ending_once_then_searches_new_episodes(
    database, monkeypatch
):
    from app.analysis.audio import SAMPLE_RATE, AudioDecodeError
    from app.analysis.media import Media
    from app.worker.tasks import run_analysis

    rng = np.random.default_rng(1)
    noise = lambda s: rng.standard_normal(round(s * SAMPLE_RATE)).astype(np.float32)  # noqa: E731
    opening_a, opening_b, ending = noise(80), noise(80), noise(80)

    def fake_episode(intro_at: int, opening=opening_a) -> np.ndarray:
        return np.concatenate([noise(intro_at), opening, noise(600), ending, noise(30)])

    # Episodes 5-7 have a new opening (second cour).
    audio = {
        f"ep{n}": fake_episode(at, op)
        for n, at, op in (
            (1, 10, opening_a), (2, 70, opening_a), (3, 40, opening_a), (4, 25, opening_a),
            (5, 30, opening_b), (6, 50, opening_b), (7, 15, opening_b),
        )
    }  # fmt: skip
    asked = []

    def fake_resolve_all(anime_id, episodes, language, fresh=False):
        asked.append((episodes, language, fresh))
        # Episode 2's first direct link is dead; the next one is used instead. Episode 4's
        # stored links all expired: only fresh ones work.
        if episodes == [4]:
            return {4: [Media("ep4")] if fresh else [Media("dead")]}
        if episodes == [3] and fresh:
            return {3: [Media("ep3-fresh")]}
        return {ep: [Media("dead")] * (ep == 2) + [Media(f"ep{ep}")] for ep in episodes}

    def fake_load_audio(source, headers):
        if source == "dead":
            raise AudioDecodeError("403 Forbidden")
        return audio[source]

    monkeypatch.setattr("app.worker.tasks.resolve_all", fake_resolve_all)
    monkeypatch.setattr("app.worker.tasks.load_audio", fake_load_audio)

    def run(job_id: str, episodes: list[int], **options):
        asked.clear()
        with sync_session() as db:
            db.add(
                AnalysisJob(id=job_id, anime_id=7, episodes=episodes, language="de-dub", **options)
            )
            db.commit()
        run_analysis(job_id)
        with sync_session() as db:
            job = db.get(AnalysisJob, job_id)
            assert job.status == JobStatus.done, job.error
            segments = {
                (s.episode, s.kind): s
                for s in db.scalars(select(SkipSegment).where(SkipSegment.anime_id == 7))
            }
            compared = {
                f.episode: f.compared_with
                for f in db.scalars(
                    select(EpisodeFingerprint).where(EpisodeFingerprint.anime_id == 7)
                )
            }
            references = sorted(
                (r.kind, r.source_episode)
                for r in db.scalars(select(ReferenceSegment).where(ReferenceSegment.anime_id == 7))
            )
        return segments, compared, references

    with sync_session() as db:
        db.add(
            SkipSegment(
                anime_id=7, episode=2, kind="ending", start_s=1, end_s=2, confidence=1,
                source="manual",
            )
        )  # fmt: skip
        db.commit()

    # First time: two episodes are compared, and their opening and ending are saved.
    rows, compared, references = run("job-1", [1, 2])
    assert asked == [([1], "de-dub", False), ([2], "de-dub", False)]
    assert rows[(1, "opening")].start_s == pytest.approx(10, abs=1.5)
    assert rows[(2, "opening")].start_s == pytest.approx(70, abs=1.5)
    assert rows[(1, "ending")].start_s == pytest.approx(690, abs=1.5)
    assert rows[(2, "ending")].source == "manual"
    assert rows[(2, "ending")].start_s == 1
    assert compared == {1: [2], 2: [1]}
    assert [kind for kind, _ in references] == ["ending", "opening"]

    # Next episodes are searched for the saved opening/ending: nothing is compared, and only
    # the new episode is downloaded.
    rows, compared, _ = run("job-3", [3])
    assert asked == [([3], "de-dub", False)]
    assert rows[(3, "opening")].start_s == pytest.approx(40, abs=1.5)
    assert rows[(3, "opening")].end_s == pytest.approx(120, abs=1.5)
    assert rows[(3, "ending")].start_s == pytest.approx(720, abs=1.5)
    assert compared == {1: [2], 2: [1], 3: []}

    # Stored links that no longer play are replaced by fresh ones once.
    rows, compared, _ = run("job-4", [4])
    assert asked == [([4], "de-dub", False), ([4], "de-dub", True)]
    assert rows[(4, "opening")].start_s == pytest.approx(25, abs=1.5)
    assert compared[4] == []

    # A new opening isn't found by the saved one: the episode is compared with the nearest
    # analysed one (no download), which only shares the ending.
    rows, compared, references = run("job-5", [5])
    assert asked == [([5], "de-dub", False)]
    assert (5, "opening") not in rows
    assert rows[(5, "ending")].start_s == pytest.approx(710, abs=1.5)
    assert compared[5] == [4]
    assert len(references) == 2

    # The next episode shares it with episode 5: it's found, saved as a second opening...
    rows, compared, references = run("job-6", [6])
    assert rows[(6, "opening")].start_s == pytest.approx(50, abs=1.5)
    assert rows[(5, "opening")].start_s == pytest.approx(30, abs=1.5)  # the partner gains it
    assert [kind for kind, _ in references].count("opening") == 2

    # ...and from then on found directly.
    rows, compared, _ = run("job-7", [7])
    assert asked == [([7], "de-dub", False)]
    assert rows[(7, "opening")].start_s == pytest.approx(15, abs=1.5)
    assert compared[7] == []

    # Retrying an episode with a wrong result downloads it again from fresh links and
    # replaces the result; a wrong time that isn't found again is removed.
    with sync_session() as db:
        db.execute(
            update(SkipSegment)
            .where(SkipSegment.anime_id == 7, SkipSegment.episode == 3)
            .values(start_s=5, end_s=6)
        )
        db.commit()
    # (This time the source has a version of episode 3 without the ending.)
    audio["ep3-fresh"] = np.concatenate([noise(40), opening_a, noise(600)])
    rows, compared, _ = run("job-8", [3], redownload=True)
    assert asked == [([3], "de-dub", True)]
    assert rows[(3, "opening")].start_s == pytest.approx(40, abs=1.5)
    assert (3, "ending") not in rows

    # Comparing instead of using the saved fingerprints (no download: all are saved).
    rows, compared, _ = run("job-9", [3], compare=True)
    assert asked == []
    assert rows[(3, "opening")].start_s == pytest.approx(40, abs=1.5)
    assert compared[3] == [4]  # the nearest analysed episode (the next one on a tie)


def test_worker_marks_job_failed_when_media_missing(database):
    from app.worker.tasks import run_analysis

    with sync_session() as db:
        db.add(AnalysisJob(id="job-2", anime_id=8, episodes=[1, 2]))
        db.commit()

    run_analysis("job-2")

    with sync_session() as db:
        job = db.get(AnalysisJob, "job-2")
        assert job.status == JobStatus.failed
        assert "No direct stream for anime 8 episode 1:" in job.error
        assert job.finished_at is not None


async def test_auto_analysis_only_queues_what_is_missing(client, user, monkeypatch):
    queued = []

    class FakeQueue:
        def enqueue(self, func, *args, **kwargs):
            queued.append(args)

    monkeypatch.setattr("app.api.anime.analysis_queue", lambda: FakeQueue())
    with sync_session() as db:
        db.execute(delete(Anime).where(Anime.id == 5))
        db.add(Anime(id=5, title="Five", num_episodes=3, genres=[]))
        db.commit()

    async def auto(episode):
        body = {"episode": episode, "language": "de-dub"}
        return (await client.post("/anime/5/analyze/auto", json=body)).json()

    first = await auto(1)
    assert (first["job"]["episodes"], first["job"]["language"]) == ([1, 2], "de-dub")
    assert (await auto(1)) == {"cached": True, "job": None}  # already waiting

    fp = {"language": "de-dub", "hashes": b"", "valid": b"", "frames": 0, "hop_seconds": 0.1}
    with sync_session() as db:
        db.get(AnalysisJob, first["job"]["id"]).status = JobStatus.done
        db.add(EpisodeFingerprint(anime_id=5, episode=1, compared_with=[2], **fp))
        db.add(EpisodeFingerprint(anime_id=5, episode=2, compared_with=[1], **fp))
        db.add(
            SkipSegment(
                anime_id=5, episode=2, kind="opening", start_s=85, end_s=175, confidence=0.9,
                source="analysis",
            )
        )  # fmt: skip
        db.commit()

    assert (await auto(2))["job"]["episodes"] == [3]  # episode 2 is done, 3 is new
    overview = (await client.get("/anime/5/analysis")).json()
    assert [(e["episode"], e["analysed"]) for e in overview["episodes"]] == [(1, True), (2, True)]
    assert overview["episodes"][1]["segments"][0]["start_s"] == 85
    assert [j["episodes"] for j in overview["running"]] == [[3]]

    with sync_session() as db:
        db.add(
            SkipSegment(
                anime_id=5, episode=3, kind="ending", start_s=1300, end_s=1390, confidence=1,
                source="manual",
            )
        )  # fmt: skip
        db.execute(delete(AnalysisJob))
        db.commit()
    assert (await auto(3)) == {"cached": True, "job": None}  # last episode, has data
    assert len(queued) == 2
