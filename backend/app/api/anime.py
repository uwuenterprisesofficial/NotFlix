import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, OptionalUser
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
    Progress,
    ProgressUpdate,
    ReferenceOut,
    SkipSegmentOut,
)
from app.services import catalog, mal
from app.services.sync import access_token
from app.worker.queue import analysis_queue

router = APIRouter(tags=["anime"])


@router.get("/anime/{anime_id}", response_model=AnimeDetail)
async def anime_detail(anime_id: int, user: OptionalUser, db: DB):
    anime = await catalog.get_anime(db, anime_id)
    if anime is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
    entry = None
    if user is not None:
        entry = await db.scalar(
            select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id == anime_id)
        )
    return catalog.to_detail(anime, entry)


@router.get("/anime/{anime_id}/episodes/{episode}", response_model=EpisodeOut)
async def episode_detail(anime_id: int, episode: int, db: DB):
    segments = await db.scalars(
        select(SkipSegment)
        .where(SkipSegment.anime_id == anime_id, SkipSegment.episode == episode)
        .order_by(SkipSegment.start_s)
    )
    return EpisodeOut(
        anime_id=anime_id,
        episode=episode,
        skip_segments=[SkipSegmentOut.model_validate(s) for s in segments],
    )


@router.put("/anime/{anime_id}/progress", response_model=Progress)
async def update_progress(anime_id: int, body: ProgressUpdate, user: CurrentUser, db: DB):
    """Record watched episodes locally and on MyAnimeList."""
    anime = await catalog.get_anime(db, anime_id)
    if anime is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anime not found")
    finished = anime.num_episodes is not None and body.episodes_watched >= anime.num_episodes
    new_status = ListStatus.completed if finished else ListStatus.watching

    try:
        async with mal.MalClient(await access_token(db, user)) as client:
            result = await client.update_my_list_status(
                anime_id, status=new_status.value, num_watched_episodes=body.episodes_watched
            )
    except mal.MalError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    entry = await db.scalar(
        select(ListEntry).where(ListEntry.user_id == user.id, ListEntry.anime_id == anime_id)
    )
    if entry is None:
        entry = ListEntry(user_id=user.id, anime_id=anime_id)
        db.add(entry)
    entry.status = result.get("status", new_status)
    entry.episodes_watched = result.get("num_episodes_watched", body.episodes_watched)
    entry.score = result.get("score", entry.score or 0)
    await db.commit()
    return Progress(status=entry.status, episodes_watched=entry.episodes_watched, score=entry.score)


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
        "app.worker.tasks.run_analysis", job.id, job_id=job.id, job_timeout=3600
    )
    return job


async def _running_jobs(db: DB, anime_id: int) -> list[AnalysisJob]:
    jobs = await db.scalars(
        select(AnalysisJob)
        .where(
            AnalysisJob.anime_id == anime_id,
            AnalysisJob.status.in_([JobStatus.queued, JobStatus.running]),
        )
        .order_by(AnalysisJob.created_at)
    )
    return list(jobs)


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

    with_segments = set(
        await db.scalars(
            select(SkipSegment.episode).where(
                SkipSegment.anime_id == anime_id, SkipSegment.episode.in_(wanted)
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
