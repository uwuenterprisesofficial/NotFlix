from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, OptionalUser
from app.models import Anime, ListEntry, ListStatus, Recommendation
from app.schemas import AnimeDetail, BrowseResponse, Row
from app.services import catalog, mal
from app.services.taste import predictor_for

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
    predictor = await predictor_for(db, user)

    def card(anime: Anime, reason: str | None = None):
        return catalog.to_card(anime, entries.get(anime.id), reason, predictor)

    def detail(anime: Anime, reason: str | None = None):
        return catalog.to_detail(anime, entries.get(anime.id), reason, predictor)

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
                items=[card(a) for a in watching],
            ),
            Row(
                id="recommended",
                title="Recommended for You",
                items=[card(a, r.reason) for r, a in recs],
            ),
            Row(
                id="my-list",
                title="My List",
                items=[card(a) for a in by_status.get(ListStatus.plan_to_watch, [])],
            ),
            Row(
                id="watch-again",
                title="Watch Again",
                items=[card(a) for a in favourites[:20]],
            ),
        ]
        if recs:
            rec, anime = recs[0]
            hero = detail(anime, rec.reason)
        elif watching:
            hero = detail(watching[0])

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
                    items=[card(a) for a in ranked],
                )
            )
            if hero is None and ranked:
                hero = detail(ranked[0])

    return BrowseResponse(
        hero=hero,
        rows=[r for r in rows if r.items],
        signed_in=user is not None,
        mal_configured=catalog.mal_configured(),
    )
