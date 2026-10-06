from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api import friends
from app.api.admin import is_admin
from app.api.deps import DB, CurrentUser, ListUser
from app.api.search import _from_catalogue
from app.models import Anime, ListEntry, ListStatus
from app.schemas import (
    AccountOut,
    LibraryResponse,
    Me,
    ResumeOut,
    Row,
    StatsStatusOut,
    SyncResult,
)
from app.services import (
    anilist_account,
    catalog,
    list_writer,
    mal,
    positions,
    related,
    stats_jobs,
    sync_jobs,
)
from app.services.sync import sync_user
from app.services.taste import predictor_for

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=Me)
async def me(user: CurrentUser, db: DB):
    return Me(
        id=user.id,
        name=user.name,
        picture=user.picture,
        last_synced_at=user.last_synced_at,
        guest=user.is_guest,
        admin=is_admin(user),
        mal=AccountOut(name=user.mal_name) if user.has_mal else None,
        anilist=AccountOut(name=user.anilist_name) if user.has_anilist else None,
        writing=list_writer.progress(user.id),
        syncing=sync_jobs.running(user.id),
        recommendations_unseen=await friends.unseen(db, user.id),
    )


@router.post("/sync", response_model=SyncResult)
async def sync(user: ListUser, db: DB):
    try:
        # A sync already running in the background (after signing in): its result.
        if sync_jobs.running(user.id) and (result := await sync_jobs.wait(user.id)) is not None:
            return result
        result = await sync_user(db, user)
    except (mal.MalError, anilist_account.AniListError) as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    # The statistics of the new list are ready by the time the page is opened.
    stats_jobs.clear_failure(user.id)
    stats_jobs.start(user.id)
    return result


RELATED_MAX = 60
# On the list in a way that counts as seen (or being seen): not offered as related.
ON_LIST_SEEN = {ListStatus.completed, ListStatus.watching, ListStatus.on_hold, ListStatus.dropped}


@router.get("/library", response_model=LibraryResponse)
async def library(user: ListUser, db: DB):
    """The My List page: what the user is watching (most recent first), what of their list airs
    this season, what they plan to watch, and shows related to what they watched (prequels,
    sequels, films, side stories) that aren't on their list yet. Relations come from AniList and
    are cached; ones not cached yet are fetched meanwhile (`related_pending`)."""
    predictor = await predictor_for(db, user)
    listed = (
        await db.execute(
            select(ListEntry, Anime)
            .join(Anime, Anime.id == ListEntry.anime_id)
            .where(ListEntry.user_id == user.id)
            .order_by(ListEntry.updated_at.desc().nulls_last())
        )
    ).all()
    entries = {anime.id: entry for entry, anime in listed}

    def card(anime: Anime, reason: str | None = None):
        return catalog.to_card(anime, entries.get(anime.id), reason, predictor)

    def having(*statuses: str) -> list[Anime]:
        return [anime for entry, anime in listed if entry.status in statuses]

    watching = having(ListStatus.watching)
    season = [
        a
        for a in having(ListStatus.watching, ListStatus.plan_to_watch, ListStatus.on_hold)
        if a.status == "currently_airing"
    ]
    planned = having(ListStatus.plan_to_watch)

    # Related to what was watched (the most recently watched first).
    watched = having(ListStatus.watching, ListStatus.completed)
    relations = await related.cached([a.id for a in watched])
    related.ensure(user.id, [a.id for a in watched if a.id not in relations])
    offered: dict[int, tuple[str, str, dict]] = {}
    for anime in watched:
        for found in relations.get(anime.id, []):
            row = found["row"]
            other = entries.get(row["id"])
            if row["id"] in offered or (other is not None and other.status in ON_LIST_SEEN):
                continue
            if other is not None and other.status == ListStatus.plan_to_watch:
                continue  # in "Plan to watch" already
            offered[row["id"]] = (found["relation"], anime.title_en or anime.title, row)
    ids = list(offered)[:RELATED_MAX]
    shows = await _from_catalogue(db, ids, {i: offered[i][2] for i in ids})
    related_cards = [card(a, f"related:{offered[a.id][0]}:{offered[a.id][1]}") for a in shows]

    continue_cards = [card(a) for a in watching]
    saved = await positions.for_shows(db, user.id, [a.id for a in watching])
    for c in continue_cards:
        if c.id in saved:
            c.resume = ResumeOut.model_validate(saved[c.id])

    return LibraryResponse(
        sections=[
            Row(id="continue", title="Continue Watching", items=continue_cards),
            Row(id="season", title="Airing This Season", items=[card(a) for a in season]),
            Row(id="planned", title="Plan to Watch", items=[card(a) for a in planned]),
            Row(id="related", title="Related to What You Watched", items=related_cards),
        ],
        related_pending=related.loading(user.id),
    )


@router.get("/stats", response_model=StatsStatusOut)
async def my_stats(user: ListUser):
    """Statistics about the user's list, compared with MAL's community scores. Computed in the
    background: poll while the status is "loading"."""
    return await stats_jobs.status(user)


@router.post("/stats/refresh", response_model=StatsStatusOut)
async def refresh_stats(user: ListUser):
    """Compute the statistics again (e.g. after a failure)."""
    await stats_jobs.forget(user.id)
    stats_jobs.clear_failure(user.id)
    return await stats_jobs.status(user)
