from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.schemas import AccountOut, Me, StatsStatusOut, SyncResult
from app.services import anilist_account, list_writer, mal, stats_jobs
from app.services.sync import sync_user

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=Me)
async def me(user: CurrentUser):
    return Me(
        id=user.id,
        name=user.name,
        picture=user.picture,
        last_synced_at=user.last_synced_at,
        mal=AccountOut(name=user.mal_name) if user.has_mal else None,
        anilist=AccountOut(name=user.anilist_name) if user.has_anilist else None,
        writing=list_writer.progress(user.id),
    )


@router.post("/sync", response_model=SyncResult)
async def sync(user: CurrentUser, db: DB):
    try:
        result = await sync_user(db, user)
    except (mal.MalError, anilist_account.AniListError) as e:
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
