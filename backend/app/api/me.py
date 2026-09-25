from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.schemas import Me, StatsOut, SyncResult
from app.services import mal, stats, taste
from app.services.sync import sync_user

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=Me)
async def me(user: CurrentUser):
    return user


@router.post("/sync", response_model=SyncResult)
async def sync(user: CurrentUser, db: DB):
    try:
        return await sync_user(db, user)
    except mal.MalError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e


@router.get("/stats", response_model=StatsOut)
async def my_stats(user: CurrentUser, db: DB):
    """Statistics about the user's list, compared with MAL's community scores."""
    rated = await taste.load_rated(db, user.id)
    return stats.compute(rated, await taste.predictor_for(db, user))
