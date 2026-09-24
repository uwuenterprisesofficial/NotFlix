import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, OptionalUser
from app.models import AnalysisJob, JobStatus, ListEntry, ListStatus, SkipSegment
from app.providers.base import find_sources
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnimeDetail,
    EpisodeOut,
    JobOut,
    Progress,
    ProgressUpdate,
    SkipSegmentOut,
    SourceOut,
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
    sources = await find_sources(db, anime_id, episode)
    return EpisodeOut(
        anime_id=anime_id,
        episode=episode,
        sources=[SourceOut(provider=s.provider, kind=s.kind, url=s.url) for s in sources],
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
    """Queue opening/ending detection. Episodes analysed by an earlier job are skipped."""
    episodes = body.episodes
    if not body.force:
        done_jobs = await db.scalars(
            select(AnalysisJob).where(
                AnalysisJob.anime_id == anime_id, AnalysisJob.status == JobStatus.done
            )
        )
        analysed = {ep for job in done_jobs for ep in job.episodes}
        pending = [ep for ep in episodes if ep not in analysed]
        if not pending:
            return AnalyzeResponse(cached=True, job=None)
        if len(pending) == 1:
            # Detection needs a second episode to compare against; reuse an analysed one.
            reference = next(ep for ep in episodes if ep != pending[0])
            pending = sorted([pending[0], reference])
        episodes = pending

    job = AnalysisJob(id=str(uuid.uuid4()), anime_id=anime_id, episodes=episodes)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    analysis_queue().enqueue(
        "app.worker.tasks.run_analysis", job.id, job_id=job.id, job_timeout=3600
    )
    return AnalyzeResponse(cached=False, job=JobOut.model_validate(job))


@router.get("/analysis/jobs/{job_id}", response_model=JobOut)
async def analysis_job(job_id: str, db: DB):
    job = await db.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job
