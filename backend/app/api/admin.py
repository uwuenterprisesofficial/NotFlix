"""The admin page: what the background machinery is doing.

- RQ workers and queues (intro/outro analysis, catalogue), with recently failed jobs.
- What runs inside the API process: provider scans (with their progress), statistics,
  writes to the other list, release calendar refreshes, Watch Together rooms.
- Providers: whether they're skipped after a connection failure, how their recent scans went
  and why the last ones failed.
- Intro/outro analysis jobs, and a few counts of what's stored.

Admins are the users named in ADMINS (MAL/AniList names or ids); without it, anyone signed in
with a list.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from rq import Queue, Worker
from rq.job import Job
from sqlalchemy import delete, func, select

from app.api.deps import DB, CurrentUser
from app.core import http as shared_http
from app.core.cache import redis
from app.core.config import get_settings
from app.models import (
    AnalysisJob,
    Anime,
    AnimeSynopsis,
    EpisodeSource,
    ListEntry,
    SourceScan,
    StreamFailure,
    User,
)
from app.providers import base as providers_base
from app.services import airing, list_writer, source_scan, stats_jobs
from app.worker.queue import ANALYSIS_QUEUE, CATALOG_QUEUE, analysis_queue

router = APIRouter(prefix="/admin", tags=["admin"])

RECENT = timedelta(hours=24)
FAILED_JOBS_SHOWN = 8


def is_admin(user: User | None) -> bool:
    if user is None or user.is_guest:
        return False
    names = {n.strip().lower() for n in get_settings().admins.split(",") if n.strip()}
    if not names:
        return True
    own = {str(user.id), (user.mal_name or "").lower(), (user.anilist_name or "").lower()}
    return bool(names & (own - {""}))


async def admin_user(user: CurrentUser) -> User:
    if not is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only (see ADMINS)")
    return user


AdminUser = Annotated[User, Depends(admin_user)]


def _job(job: Job | None) -> dict[str, Any] | None:
    if job is None:
        return None
    result = job.latest_result()
    error = ((result.exc_string if result else None) or "").strip().splitlines()
    return {
        "id": job.id,
        "function": (job.func_name or "").rsplit(".", 1)[-1],
        "args": [a for a in (job.args or []) if isinstance(a, int | str)][:3],
        "enqueued_at": job.enqueued_at,
        "started_at": job.started_at,
        "ended_at": job.ended_at,
        "error": error[-1][:300] if error else None,
    }


def _rq() -> dict[str, Any]:
    """Workers and queues (RQ's client is synchronous: run in a thread)."""
    connection = analysis_queue().connection
    workers = []
    for w in Worker.all(connection=connection):
        workers.append(
            {
                "name": w.name,
                "state": w.get_state(),
                "queues": w.queue_names(),
                "job": _job(w.get_current_job()),
                "last_heartbeat": w.last_heartbeat,
                "birth": w.birth_date,
                "successful": w.successful_job_count,
                "failed": w.failed_job_count,
            }
        )
    queues = []
    for name in (ANALYSIS_QUEUE, CATALOG_QUEUE):
        q = Queue(name, connection=connection)
        failed_ids = q.failed_job_registry.get_job_ids(0, FAILED_JOBS_SHOWN - 1)
        failed = [_job(j) for j in Job.fetch_many(failed_ids, connection=connection) if j]
        queues.append(
            {
                "name": name,
                "queued": q.count,
                "started": q.started_job_registry.count,
                "failed": q.failed_job_registry.count,
                "finished": q.finished_job_registry.count,
                "scheduled": q.scheduled_job_registry.count,
                "recent_failures": failed,
            }
        )
    return {"workers": workers, "queues": queues}


async def _titles(db: DB, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = await db.execute(select(Anime.id, Anime.title_en, Anime.title).where(Anime.id.in_(ids)))
    return {i: en or title for i, en, title in rows}


@router.get("/status")
async def admin_status(_: AdminUser, db: DB) -> dict[str, Any]:
    now = datetime.now(UTC)
    try:
        rq = await asyncio.to_thread(_rq)
    except Exception as e:  # Redis down: the rest is still worth seeing
        rq = {"workers": [], "queues": [], "error": str(e)[:300]}

    # Inside the API process.
    scans = [
        {
            "anime_id": anime_id,
            "provider": provider,
            "stored": len(s.stored),
            "total": len(s.episodes),
            "stepwise": s.stepwise,
        }
        for (anime_id, provider), s in list(source_scan._running.items())
    ]
    stats = [
        {"user_id": user_id, **state}
        for user_id, state in list(stats_jobs._progress.items())
        if stats_jobs.running(user_id) or state.get("status") == "failed"
    ]
    writers = [
        {"user_id": user_id, **(list_writer.progress(user_id) or {})}
        for user_id in list(list_writer._running)
    ]
    rooms = 0
    async for _key in redis().scan_iter("together:presence:*"):
        rooms += 1

    # Providers: backoffs, and how their scans went lately.
    backoffs = providers_base.backoffs()
    since = now - RECENT
    counts = await db.execute(
        select(SourceScan.provider, SourceScan.status, func.count())
        .where(SourceScan.started_at >= since)
        .group_by(SourceScan.provider, SourceScan.status)
    )
    by_provider: dict[str, dict[str, int]] = {}
    for provider, scan_status, n in counts:
        by_provider.setdefault(provider, {})[scan_status] = n
    failed_scans = list(
        await db.scalars(
            select(SourceScan)
            .where(SourceScan.status == "failed")
            .order_by(SourceScan.finished_at.desc().nulls_last())
            .limit(20)
        )
    )
    enabled = [p.name for p in providers_base.enabled_providers()]
    providers = [
        {
            "name": name,
            "enabled": name in enabled,
            "backoff_s": round(backoffs[name]) if name in backoffs else None,
            "scans_24h": by_provider.get(name, {}),
            "last_error": next(
                (
                    {"anime_id": s.anime_id, "error": s.error, "at": s.finished_at}
                    for s in failed_scans
                    if s.provider == name
                ),
                None,
            ),
        }
        for name in dict.fromkeys([*enabled, *by_provider])
    ]

    job_counts = dict(
        (await db.execute(select(AnalysisJob.status, func.count()).group_by(AnalysisJob.status)))
        .tuples()
        .all()
    )
    recent_jobs = list(
        await db.scalars(select(AnalysisJob).order_by(AnalysisJob.created_at.desc()).limit(10))
    )

    ids = {s["anime_id"] for s in scans} | {s.anime_id for s in failed_scans}
    ids |= {j.anime_id for j in recent_jobs}
    titles = await _titles(db, ids)

    counts_row = {
        "users": await db.scalar(select(func.count()).select_from(User)),
        "list_entries": await db.scalar(select(func.count()).select_from(ListEntry)),
        "anime": await db.scalar(select(func.count()).select_from(Anime)),
        "anime_incomplete": await db.scalar(
            select(func.count()).select_from(Anime).where(Anime.enriched_at.is_(None))
        ),
        "synopses": await db.scalar(select(func.count()).select_from(AnimeSynopsis)),
        "episode_sources": await db.scalar(select(func.count()).select_from(EpisodeSource)),
        "stream_failures": await db.scalar(select(func.count()).select_from(StreamFailure)),
    }
    info = await redis().info("memory")

    return {
        "now": now,
        "rq": rq,
        "api": {
            "scans": [{**s, "title": titles.get(s["anime_id"])} for s in scans],
            "stats": stats,
            "list_writers": writers,
            "calendar_weeks_refreshing": sorted(airing._refreshing),
            "airing_checks": len(airing._checking),
            "rooms_open": rooms,
            "http_clients": shared_http.names(),
        },
        "providers": providers,
        "failed_scans": [
            {
                "anime_id": s.anime_id,
                "title": titles.get(s.anime_id),
                "provider": s.provider,
                "error": s.error,
                "at": s.finished_at,
            }
            for s in failed_scans
        ],
        "analysis": {
            "counts": job_counts,
            "recent": [
                {
                    "id": j.id,
                    "anime_id": j.anime_id,
                    "title": titles.get(j.anime_id),
                    "episodes": j.episodes,
                    "status": j.status,
                    "error": j.error,
                    "created_at": j.created_at,
                    "finished_at": j.finished_at,
                }
                for j in recent_jobs
            ],
        },
        "counts": counts_row,
        "redis_memory": info.get("used_memory_human"),
    }


@router.post("/providers/{name}/retry", status_code=status.HTTP_204_NO_CONTENT)
async def retry_provider(name: str, _: AdminUser, db: DB) -> None:
    """Stop skipping a provider after its connection failure, and forget its failed scans, so
    the next visit to a show scans it again."""
    providers_base.clear_backoff(name)
    await db.execute(
        delete(SourceScan).where(SourceScan.provider == name, SourceScan.status == "failed")
    )
    await db.commit()
