import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentUser, ListUser, OptionalUser
from app.core.cache import redis
from app.models import (
    AnalysisJob,
    EpisodeFingerprint,
    JobStatus,
    ListEntry,
    ListStatus,
    ReferenceSegment,
    SkipSegment,
)
from app.schemas import (
    AnalysisOverview,
    AnalyzeRequest,
    AnalyzeResponse,
    AnimeDetail,
    AutoAnalyzeRequest,
    EpisodeAnalysisOut,
    EpisodeOut,
    JobOut,
    ListStatusUpdate,
    PositionIn,
    Progress,
    ProgressUpdate,
    ReferenceOut,
    RelatedShow,
    ResumeOut,
    ScoreUpdate,
    SkipSegmentOut,
    StoryOut,
    SynopsisOut,
)
from app.services import airing, aniskip, catalog, list_status, positions, related, synopsis
from app.services.taste import Predictor, link_franchise, predictor_for
from app.worker.queue import analysis_queue, stop_job, timeout_message, timeout_seconds

log = logging.getLogger(__name__)
router = APIRouter(tags=["anime"])
# How long past the timeout a running job may go unreported before it counts as dead.
TIMEOUT_GRACE = timedelta(minutes=1)
ANISKIP_CONFIDENCE = 0.5  # crowd-sourced, for another release of the episode
# An episode analysed without finding its opening is tried again at most this often.
RETRY_ANALYSIS_S = 24 * 3600


# How long a show's page waits for its relations (AniList) when they aren't cached.
RELATIONS_WAIT_S = 4


async def _own_franchise(predictor: Predictor, anime_id: int) -> None:
    """The show's own relations (a moment's wait when they aren't cached): its prequels and
    sequels the user scored count for its prediction, even when their relations aren't known."""
    relations = (await related.cached([anime_id])).get(anime_id)
    if relations is None:
        try:
            await asyncio.wait_for(related.fetch([anime_id]), RELATIONS_WAIT_S)
        except (TimeoutError, httpx.HTTPError, ValueError) as e:
            log.info("Relations of anime %s: %s", anime_id, e)
        relations = (await related.cached([anime_id])).get(anime_id)
    link_franchise(predictor.context, anime_id, relations or [])


@router.get("/anime/{anime_id}", response_model=AnimeDetail)
async def anime_detail(anime_id: int, user: OptionalUser, db: DB, lang: str = "en"):
    """A show's details; with `lang`, the synopsis in that language if it's already known
    (GET /anime/{id}/synopsis looks it up)."""
    anime = await catalog.get_anime(db, anime_id)
    if anime is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
    entry = None
    if user is not None:
        entry = await db.scalar(
            select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id == anime_id)
        )
    predictor = await predictor_for(db, user)
    if predictor is not None and catalog.predicts(entry):
        await _own_franchise(predictor, anime_id)
    detail = catalog.to_detail(anime, entry, predictor=predictor)
    if user is not None and (position := await positions.get(db, user.id, anime_id)):
        detail.resume = ResumeOut.model_validate(position)
    detail.aired_episodes = await airing.aired_episodes(db, anime)
    if anime.next_episode_at and anime.next_episode_at > datetime.now(UTC):
        detail.next_episode, detail.next_episode_at = anime.next_episode, anime.next_episode_at
    else:
        detail.next_episode = detail.next_episode_at = None
    if synopsis.supported(lang):
        row = await synopsis.stored(db, anime_id, lang)
        if row is not None and row.synopsis:
            detail.synopsis, detail.synopsis_language = row.synopsis, lang
    return detail


@router.get("/anime/{anime_id}/story", response_model=StoryOut)
async def anime_story(anime_id: int, user: OptionalUser, db: DB):
    """The show's prequels and sequels in order (with the show itself), and its other relations
    (films, side stories, spin-offs), from AniList (cached for a week)."""
    from app.api.search import _cards, _from_catalogue

    anime = await catalog.get_anime(db, anime_id)
    if anime is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
    before, after, other, complete = await related.story(anime_id)
    found = [*before, *after, *other]
    rows = {r["row"]["id"]: r["row"] for r in found}
    ids = [r["row"]["id"] for r in found]
    shows = await _from_catalogue(db, [anime_id, *ids], rows)
    cards = {c.id: c for c in await _cards(db, user, shows)}

    def items(relations: list[dict]) -> list[RelatedShow]:
        return [
            RelatedShow(relation=r["relation"], anime=cards[r["row"]["id"]])
            for r in relations
            if r["row"]["id"] in cards
        ]

    current = [RelatedShow(relation="CURRENT", anime=cards[anime_id])] if anime_id in cards else []
    story = [*items(before), *current, *items(after)] if before or after else []
    return StoryOut(story=story, other=items(other), complete=complete)


@router.get("/anime/{anime_id}/synopsis", response_model=SynopsisOut)
async def anime_synopsis(anime_id: int, db: DB, lang: str = Query(pattern=r"^[a-z]{2}$")):
    """The synopsis in `lang` (German from AniWorld), else MAL's English one. May take a few
    seconds the first time, while the show is found on AniWorld."""
    anime = await catalog.get_anime(db, anime_id)
    if anime is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
    text = await synopsis.localized(db, anime, lang)
    if text:
        return SynopsisOut(language=lang, synopsis=text)
    return SynopsisOut(language="en", synopsis=anime.synopsis)


@router.get("/anime/{anime_id}/episodes/{episode}", response_model=EpisodeOut)
async def episode_detail(anime_id: int, episode: int, db: DB):
    """The episode's opening/ending times: detected or entered ones, else AniSkip's (stored
    until the detection finds the exact ones)."""
    query = (
        select(SkipSegment)
        .where(SkipSegment.anime_id == anime_id, SkipSegment.episode == episode)
        .order_by(SkipSegment.start_s)
    )
    segments = list(await db.scalars(query))
    have = {s.kind for s in segments}
    if "opening" not in have:
        found = [f for f in await aniskip.skip_times(anime_id, episode) if f.kind not in have]
        for f in found:
            db.add(
                SkipSegment(
                    anime_id=anime_id, episode=episode, kind=f.kind, start_s=f.start_s,
                    end_s=f.end_s, confidence=ANISKIP_CONFIDENCE, source="aniskip",
                )
            )  # fmt: skip
        if found:
            await db.commit()
            segments = list(await db.scalars(query))
    return EpisodeOut(
        anime_id=anime_id,
        episode=episode,
        skip_segments=[SkipSegmentOut.model_validate(s) for s in segments],
    )


@router.put("/anime/{anime_id}/progress", response_model=Progress)
async def update_progress(anime_id: int, body: ProgressUpdate, user: ListUser, db: DB):
    """Record watched episodes locally and on every linked list (MyAnimeList, AniList)."""
    anime = await catalog.get_anime(db, anime_id)
    if anime is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
    finished = anime.num_episodes is not None and body.episodes_watched >= anime.num_episodes
    new_status = ListStatus.completed if finished else ListStatus.watching
    try:
        saved = await list_status.save(db, user, anime_id, new_status, body.episodes_watched)
    except list_status.NotSaved as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    # A watched episode has nothing to resume.
    await positions.clear(db, user.id, anime_id, up_to_episode=body.episodes_watched)
    return _progress(saved)


def _progress(saved: list_status.Saved) -> Progress:
    entry = saved.entry
    return Progress(
        status=entry.status,
        episodes_watched=entry.episodes_watched,
        score=entry.score,
        failed=saved.failed,
    )


@router.get("/anime/{anime_id}/position", response_model=ResumeOut | None)
async def get_position(anime_id: int, user: CurrentUser, db: DB):
    """Where the user stopped in the episode they're watching of this show (or null)."""
    position = await positions.get(db, user.id, anime_id)
    return ResumeOut.model_validate(position) if position else None


# POST as well: navigator.sendBeacon (used when the tab closes) can only POST.
@router.api_route("/anime/{anime_id}/position", methods=["PUT", "POST"], status_code=204)
async def save_position(anime_id: int, body: PositionIn, user: CurrentUser, db: DB) -> None:
    """Remember where playback is (replacing the show's earlier episode). Near the end the
    position is dropped: the episode is finished."""
    await positions.save(db, user.id, anime_id, body.episode, body.position_s, body.duration_s)


@router.delete("/anime/{anime_id}/position", status_code=204)
async def clear_position(anime_id: int, user: CurrentUser, db: DB) -> None:
    await positions.clear(db, user.id, anime_id)


@router.put("/anime/{anime_id}/list", response_model=Progress)
async def set_list_status(anime_id: int, body: ListStatusUpdate, user: ListUser, db: DB):
    """Put a show on the user's lists with this status (e.g. "Plan to watch" from a preview
    card). Episodes watched so far are kept."""
    if await catalog.get_anime(db, anime_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
    try:
        saved = await list_status.save(db, user, anime_id, body.status)
    except list_status.NotSaved as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return _progress(saved)


@router.put("/anime/{anime_id}/score", response_model=Progress)
async def set_score(anime_id: int, body: ScoreUpdate, user: ListUser, db: DB):
    """Score a show (1-10; 0 removes the score) on every linked list. A show that isn't on
    the list yet goes there as completed (scoring it says it was watched)."""
    if await catalog.get_anime(db, anime_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
    entry = await db.scalar(
        select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id == anime_id)
    )
    current = entry.status if entry is not None else ListStatus.completed
    try:
        saved = await list_status.save(db, user, anime_id, current, score=body.score)
    except list_status.NotSaved as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return _progress(saved)


@router.post("/anime/{anime_id}/analyze", response_model=AnalyzeResponse)
async def analyze(anime_id: int, body: AnalyzeRequest, user: CurrentUser, db: DB):
    """Queue opening/ending detection for these episodes, replacing their earlier results.
    A single episode needs something to be matched against: a saved opening/ending
    fingerprint, or (to compare) another analysed episode."""
    if len(body.episodes) == 1:
        [episode] = body.episodes
        references = await db.scalar(
            select(func.count())
            .select_from(ReferenceSegment)
            .where(ReferenceSegment.anime_id == anime_id)
        )
        others = await db.scalar(
            select(func.count())
            .select_from(EpisodeFingerprint)
            .where(EpisodeFingerprint.anime_id == anime_id, EpisodeFingerprint.episode != episode)
        )
        if not others and not (references and not body.compare):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A single episode can only be analysed once an intro/outro fingerprint is "
                "saved. Pick two episodes.",
            )
    job = await _queue_analysis(
        db, anime_id, body.episodes, body.language, body.compare, body.redownload
    )
    return AnalyzeResponse(cached=False, job=JobOut.model_validate(job))


async def _queue_analysis(
    db: DB,
    anime_id: int,
    episodes: list[int],
    language: str | None,
    compare: bool = False,
    redownload: bool = False,
) -> AnalysisJob:
    job = AnalysisJob(
        id=str(uuid.uuid4()),
        anime_id=anime_id,
        episodes=episodes,
        language=language,
        compare=compare,
        redownload=redownload,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    analysis_queue().enqueue(
        "app.worker.tasks.run_analysis", job.id, job_id=job.id, job_timeout=timeout_seconds()
    )
    return job


async def _expire(db: DB, jobs: list[AnalysisJob]) -> list[AnalysisJob]:
    """Mark jobs failed that have been running for longer than the timeout plus a grace period:
    RQ stops them at the timeout, so their worker died (e.g. restarted) without saying so.
    Returns the ones still queued or running."""
    limit = datetime.now(UTC) - timedelta(seconds=timeout_seconds()) - TIMEOUT_GRACE
    changed = False
    for job in jobs:
        if job.status == JobStatus.running and job.started_at and job.started_at < limit:
            job.status, job.error = JobStatus.failed, timeout_message()
            job.finished_at = datetime.now(UTC)
            changed = True
    if changed:
        await db.commit()
    return [j for j in jobs if j.status in (JobStatus.queued, JobStatus.running)]


async def _running_jobs(db: DB, anime_id: int) -> list[AnalysisJob]:
    jobs = await db.scalars(
        select(AnalysisJob)
        .where(
            AnalysisJob.anime_id == anime_id,
            AnalysisJob.status.in_([JobStatus.queued, JobStatus.running]),
        )
        .order_by(AnalysisJob.created_at)
    )
    return await _expire(db, list(jobs))


@router.post("/anime/{anime_id}/analyze/auto", response_model=AnalyzeResponse)
async def analyze_automatically(anime_id: int, body: AutoAnalyzeRequest, user: CurrentUser, db: DB):
    """Called while an episode plays: analyse it and the next one, unless they already have
    intro/outro data or were matched before (or a job for them is already waiting)."""
    anime = await catalog.get_anime(db, anime_id)
    if anime is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
    wanted = [body.episode]
    if anime.num_episodes is None or body.episode < anime.num_episodes:
        wanted.append(body.episode + 1)

    # Done: a detected opening (AniSkip's is only a stand-in), or times entered by hand.
    with_opening = set(
        await db.scalars(
            select(SkipSegment.episode).where(
                SkipSegment.anime_id == anime_id,
                SkipSegment.episode.in_(wanted),
                or_(
                    (SkipSegment.kind == "opening") & (SkipSegment.source != "aniskip"),
                    SkipSegment.source == "manual",
                ),
            )
        )
    )
    matched = {
        fp.episode
        for fp in await db.scalars(
            select(EpisodeFingerprint).where(
                EpisodeFingerprint.anime_id == anime_id, EpisodeFingerprint.episode.in_(wanted)
            )
        )
        if fp.compared_with
    }
    # Analysed before without an opening: tried again (at most daily) once there's a saved
    # opening fingerprint to search it for, e.g. learned from other episodes since.
    has_reference = await db.scalar(
        select(func.count())
        .select_from(ReferenceSegment)
        .where(ReferenceSegment.anime_id == anime_id, ReferenceSegment.kind == "opening")
    )
    if has_reference:
        for ep in sorted(matched - with_opening):
            if await redis().set(
                f"analysis:retry:{anime_id}:{ep}", 1, ex=RETRY_ANALYSIS_S, nx=True
            ):
                matched.discard(ep)
    with_segments = with_opening
    queued = {ep for job in await _running_jobs(db, anime_id) for ep in job.episodes}
    todo = [ep for ep in wanted if ep not in with_segments | matched | queued]
    if not todo:
        return AnalyzeResponse(cached=True, job=None)
    job = await _queue_analysis(db, anime_id, todo, body.language)
    return AnalyzeResponse(cached=False, job=JobOut.model_validate(job))


@router.get("/anime/{anime_id}/analysis", response_model=AnalysisOverview)
async def analysis_overview(anime_id: int, db: DB):
    """Every episode's intro/outro times, which episodes were analysed, and pending jobs."""
    segments = await db.scalars(
        select(SkipSegment)
        .where(SkipSegment.anime_id == anime_id)
        .order_by(SkipSegment.episode, SkipSegment.start_s)
    )
    by_episode: dict[int, list[SkipSegment]] = {}
    for seg in segments:
        by_episode.setdefault(seg.episode, []).append(seg)
    rows = await db.execute(
        select(EpisodeFingerprint.episode, EpisodeFingerprint.compared_with).where(
            EpisodeFingerprint.anime_id == anime_id
        )
    )
    analysed = {episode for episode, compared_with in rows if compared_with}
    references = await db.execute(
        select(
            ReferenceSegment.id,
            ReferenceSegment.kind,
            ReferenceSegment.source_episode,
            ReferenceSegment.frames * ReferenceSegment.hop_seconds,
        )
        .where(ReferenceSegment.anime_id == anime_id)
        .order_by(ReferenceSegment.kind.desc(), ReferenceSegment.source_episode)
    )
    return AnalysisOverview(
        episodes=[
            EpisodeAnalysisOut(
                episode=ep,
                analysed=ep in analysed or ep in by_episode,
                segments=[SkipSegmentOut.model_validate(s) for s in by_episode.get(ep, [])],
            )
            for ep in sorted(analysed | set(by_episode))
        ],
        references=[
            ReferenceOut(
                id=ref_id, kind=kind, source_episode=episode, duration_s=round(duration, 1)
            )
            for ref_id, kind, episode, duration in references
        ],
        running=[JobOut.model_validate(j) for j in await _running_jobs(db, anime_id)],
    )


@router.get("/analysis/jobs/{job_id}", response_model=JobOut)
async def analysis_job(job_id: str, db: DB):
    job = await db.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    await _expire(db, [job])
    return job


@router.post("/analysis/jobs/{job_id}/stop", response_model=JobOut)
async def stop_analysis_job(job_id: str, user: CurrentUser, db: DB):
    """Stop a waiting or running analysis (e.g. one that hangs); it's marked failed. Also
    works when its worker is gone and the job only looks like it's running."""
    job = await db.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if job.status in (JobStatus.queued, JobStatus.running):
        await asyncio.to_thread(stop_job, job_id)
        await db.refresh(job)  # it may have finished meanwhile
        if job.status in (JobStatus.queued, JobStatus.running):
            job.status, job.error = JobStatus.failed, "Stopped"
            job.finished_at = datetime.now(UTC)
            await db.commit()
    return job


@router.delete(
    "/anime/{anime_id}/analysis/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_reference(anime_id: int, reference_id: int, user: CurrentUser, db: DB):
    """Forget a saved opening/ending fingerprint (e.g. a wrong one). Later analyses compare
    episodes again where no other fingerprint matches, and save what they find."""
    ref = await db.get(ReferenceSegment, reference_id)
    if ref is None or ref.anime_id != anime_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fingerprint not found")
    await db.delete(ref)
    await db.commit()
