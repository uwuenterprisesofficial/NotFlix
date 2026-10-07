"""The user's playlist (see services/playlist.py)."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import update

from app.api.deps import DB, ListUser
from app.models import User
from app.schemas import (
    PlaylistAdd,
    PlaylistItemOut,
    PlaylistOrder,
    PlaylistOut,
    PlaylistSettings,
)
from app.services import catalog, playlist
from app.services.taste import predictor_for

router = APIRouter(prefix="/me/playlist", tags=["playlist"])


async def _out(db: DB, user: User) -> PlaylistOut:
    predictor = await predictor_for(db, user)
    return PlaylistOut(
        auto_airing=user.playlist_auto_airing,
        items=[
            PlaylistItemOut(
                anime=catalog.to_card(e.anime, e.entry, None, predictor),
                episode=e.episode,
                auto=e.item.auto,
            )
            for e in await playlist.current(db, user)
        ],
    )


@router.get("", response_model=PlaylistOut)
async def get_playlist(user: ListUser, db: DB):
    return await _out(db, user)


@router.post("", response_model=PlaylistOut)
async def add(body: PlaylistAdd, user: ListUser, db: DB):
    if await catalog.get_anime(db, body.anime_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown anime")
    await playlist.add(db, user, body.anime_id)
    return await _out(db, user)


@router.delete("/{anime_id}", response_model=PlaylistOut)
async def remove(anime_id: int, user: ListUser, db: DB):
    await playlist.remove(db, user, anime_id)
    return await _out(db, user)


@router.put("/order", response_model=PlaylistOut)
async def reorder(body: PlaylistOrder, user: ListUser, db: DB):
    await playlist.reorder(db, user, body.anime_ids)
    return await _out(db, user)


@router.put("/settings", response_model=PlaylistOut)
async def settings(body: PlaylistSettings, user: ListUser, db: DB):
    await db.execute(
        update(User).where(User.id == user.id).values(playlist_auto_airing=body.auto_airing)
    )
    await db.commit()
    user.playlist_auto_airing = body.auto_airing
    return await _out(db, user)
