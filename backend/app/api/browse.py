from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, OptionalUser
from app.models import Anime, ListEntry, ListStatus, Recommendation
from app.schemas import AnimeDetail, BrowseResponse, Row
from app.services import catalog, mal

router = APIRouter(tags=["browse"])

RANKING_ROWS = [
    ("airing", "Top Airing"),
    ("bypopularity", "Most Popular"),
    ("upcoming", "Coming Soon"),
]


@router.get("/browse", response_model=BrowseResponse)
async def browse(user: OptionalUser, db: DB):
    rows: list[Row] = []
    entries: dict[int, ListEntry] = {}
    hero: AnimeDetail | None = None

    if user is not None:
        result = await db.execute(
            select(ListEntry, Anime)
            .join(Anime, Anime.id == ListEntry.anime_id)
            .where(ListEntry.user_id == user.id)
            .order_by(ListEntry.updated_at.desc().nulls_last())
        )
        by_status: dict[str, list[Anime]] = {}
        for entry, anime in result.all():
            entries[anime.id] = entry
            by_status.setdefault(entry.status, []).append(anime)

        recs = (
            await db.execute(
                select(Recommendation, Anime)
                .join(Anime, Anime.id == Recommendation.anime_id)
                .where(Recommendation.user_id == user.id)
                .order_by(Recommendation.score.desc())
            )
        ).all()

        watching = by_status.get(ListStatus.watching, [])
        favourites = sorted(
            by_status.get(ListStatus.completed, []), key=lambda a: entries[a.id].score, reverse=True
        )
        rows += [
            Row(
                id="continue",
                title="Continue Watching",
                items=[catalog.to_card(a, entries[a.id]) for a in watching],
            ),
            Row(
                id="recommended",
                title="Recommended for You",
                items=[catalog.to_card(a, reason=r.reason) for r, a in recs],
            ),
            Row(
                id="my-list",
                title="My List",
                items=[
                    catalog.to_card(a, entries[a.id])
                    for a in by_status.get(ListStatus.plan_to_watch, [])
                ],
            ),
            Row(
                id="watch-again",
                title="Watch Again",
                items=[catalog.to_card(a, entries[a.id]) for a in favourites[:20]],
            ),
        ]
        if recs:
            rec, anime = recs[0]
            hero = catalog.to_detail(anime, reason=rec.reason)
        elif watching:
            hero = catalog.to_detail(watching[0], entries[watching[0].id])

    if catalog.mal_configured():
        for ranking_type, title in RANKING_ROWS:
            try:
                ranked = await catalog.ranking(db, ranking_type)
            except mal.MalError:
                continue
            rows.append(
                Row(
                    id=ranking_type,
                    title=title,
                    items=[catalog.to_card(a, entries.get(a.id)) for a in ranked],
                )
            )
            if hero is None and ranked:
                hero = catalog.to_detail(ranked[0], entries.get(ranked[0].id))

    return BrowseResponse(
        hero=hero,
        rows=[r for r in rows if r.items],
        signed_in=user is not None,
        mal_configured=catalog.mal_configured(),
    )
