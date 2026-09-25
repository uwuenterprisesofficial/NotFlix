from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.schemas import Me, StatsStatusOut, SyncResult
from app.services import mal, stats_jobs
from app.services.sync import sync_user

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=Me)
async def me(user: CurrentUser):
    return user


@router.post("/sync", response_model=SyncResult)
async def sync(user: CurrentUser, db: DB):
    try:
        result = await sync_user(db, user)
    except mal.MalError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    # The statistics of the new list are ready by the time the page is opened.
    stats_jobs.clear_failure(user.id)
    stats_jobs.start(user.id)
    return result


@router.get("/stats", response_model=StatsStatusOut)
async def my_stats(user: CurrentUser):
    """Statistics about the user's list, compared with MAL's community scores. Computed in the
    background: poll while the status is "loading"."""
    return await stats_jobs.status(user)


@router.post("/stats/refresh", response_model=StatsStatusOut)
async def refresh_stats(user: CurrentUser):
    """Compute the statistics again (e.g. after a failure)."""
    await stats_jobs.forget(user.id)
    stats_jobs.clear_failure(user.id)
    return await stats_jobs.status(user)
