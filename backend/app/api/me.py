from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.schemas import Me, SyncResult
from app.services import mal
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
