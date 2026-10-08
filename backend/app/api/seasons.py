"""A season's page: everything starting in a season, what the user should watch of it, and how
much of it they've watched."""

from statistics import median
from typing import Literal

from fastapi import APIRouter, Path
from sqlalchemy import select

from app.api.deps import DB, OptionalUser
from app.models import Anime, ListEntry, ListStatus
from app.schemas import AnimeCard, ResumeOut, SeasonCompletion, SeasonGenre, SeasonOut
from app.services import catalog, caught_up, positions, seasons
from app.services.taste import predictor_for

router = APIRouter(tags=["seasons"])

ROW = 15
# Underrated: less popular than most of the season, yet predicted at least this well.
UNDERRATED_MIN = 7.5
UNDERRATED_MIN_MEAN = 7.6  # signed out: MAL's score instead


@router.get("/seasons/current")
async def current_season():
    year, season = seasons.current()
    return {"year": year, "season": season}


@router.get("/seasons/{year}/{season}", response_model=SeasonOut)
async def season_page(
    user: OptionalUser,
    db: DB,
    year: int = Path(ge=1917, le=2100),
    season: Literal["winter", "spring", "summer", "fall"] = Path(),
):
    shows, complete = await seasons.shows(db, year, season)
    entries: dict[int, ListEntry] = {}
    if user is not None and shows:
        entries = {
            e.anime_id: e
            for e in await db.scalars(
                select(ListEntry).where(
                    ListEntry.user_id == user.id, ListEntry.anime_id.in_([a.id for a in shows])
                )
            )
        }
    predictor = await predictor_for(db, user)
    cards = [catalog.to_card(a, entries.get(a.id), predictor=predictor) for a in shows]
    await caught_up.mark(db, cards)
    if user is not None:
        saved = await positions.for_shows(db, user.id, [c.id for c in cards])
        for c in cards:
            if c.id in saved:
                c.resume = ResumeOut.model_validate(saved[c.id])
    by_id: dict[int, Anime] = {a.id: a for a in shows}

    def unseen(c: AnimeCard) -> bool:
        return c.progress is None or c.progress.status == ListStatus.plan_to_watch

    def predicted(c: AnimeCard) -> float:
        return c.prediction.score if c.prediction else 0.0

    popularity = [a.num_list_users or 0 for a in shows]
    middle = median(popularity) if popularity else 0
    popular = [c for c in cards if (by_id[c.id].num_list_users or 0) >= middle]
    unpopular = [c for c in cards if (by_id[c.id].num_list_users or 0) < middle]

    highlights = sorted((c for c in popular if c.mean), key=lambda c: -(c.mean or 0))[:ROW]
    if predictor is not None:
        recommended = sorted(
            (c for c in cards if unseen(c) and c.prediction), key=lambda c: -predicted(c)
        )[:ROW]
        underrated = sorted(
            (c for c in unpopular if unseen(c) and predicted(c) >= UNDERRATED_MIN),
            key=lambda c: -predicted(c),
        )[:ROW]
    else:
        recommended = []
        underrated = sorted(
            (c for c in unpopular if (c.mean or 0) >= UNDERRATED_MIN_MEAN),
            key=lambda c: -(c.mean or 0),
        )[:ROW]

    aired = [c for c in cards if c.status != "not_yet_aired"]
    completion = None
    if user is not None and not user.is_guest:
        completion = SeasonCompletion(
            total=len(aired),
            watched=sum(c.caught_up for c in aired),
            watching=sum(
                1
                for c in aired
                if c.progress and c.progress.status in caught_up.STARTED and not c.caught_up
            ),
            planned=sum(
                1 for c in cards if c.progress and c.progress.status == ListStatus.plan_to_watch
            ),
        )
    totals: dict[str, list[int]] = {}
    for c in aired:
        for genre in c.genres:
            counts = totals.setdefault(genre, [0, 0])
            counts[0] += 1
            counts[1] += c.caught_up
    genres = sorted(
        (SeasonGenre(genre=g, total=t, watched=w) for g, (t, w) in totals.items()),
        key=lambda g: (-g.total, g.genre),
    )
    return SeasonOut(
        year=year,
        season=season,
        current=(year, season) == seasons.current(),
        items=cards,
        recommended=recommended,
        highlights=highlights,
        underrated=underrated,
        completion=completion,
        genres=genres,
        complete=complete,
    )
