"""Predict how a user would score a show they haven't scored, from their MyAnimeList list.

A weighted ridge regression on the user's scored shows:

    score ≈ intercept + a·(MAL mean − list average) + b·popularity + Σ weight(feature)

Features are one-hot: each genre, theme and demographic (by MAL id), the main studios, the
source material, the media type and the decade. Dropped shows the user never scored count as
low scores (with half weight). Features seen on fewer than two shows are left out, and the
ridge penalty pulls rarely seen ones towards zero, so a single loved show doesn't make its
genre a favourite.

MAL's score is held back (a strong ridge penalty on its weight): the user's own preferences
should explain their scores, not the community's. Two things the regression can't see are added
when predicting:

- the franchise: the user's scores of the show's prequels, sequels, side stories and films
  (also two steps away, e.g. season 1 for season 3): the prediction is pulled most of the way
  towards them, since a sequel of something they loved is likely loved too, and
- the shows they scored highly whose MyAnimeList community recommendations include it.

Predictions are labelled by where they fall among the (cross-validated) predictions for the
user's own list: at the top of what they watched is a MUST WATCH, at the bottom an AVOID. A
show the community rates low that fits the categories the user watches most is a GUILTY WATCH
on top of that.
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Literal

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Anime, CommunityRecommendation, ListEntry, ListStatus, TasteModel, User
from app.services.tags import category, tags_from_names

Tier = Literal["must_watch", "recommended", "maybe", "skip", "avoid"]
TIERS: tuple[Tier, ...] = ("must_watch", "recommended", "maybe", "skip", "avoid")
# Percentiles of the list's own predictions a show must reach for each tier but the last.
TIER_PERCENTILES = (85, 60, 30, 12)

MIN_SCORED = 10  # fewer scored shows than this: no predictions
MIN_FEATURE_COUNT = 2
RIDGE = 3.0  # penalty on each one-hot weight, in shows
# MAL's score: penalised per training show, which roughly halves its weight (personal taste
# should carry more).
RIDGE_MAL_PER_SHOW = 0.3
RIDGE_POPULARITY = 2.0
DROPPED_WEIGHT = 0.5
FOLDS = 5
MAX_STUDIOS = 2
MODEL_VERSION = 3  # bump to refit stored models after a change to the features

# The franchise pulls the prediction this share of the way towards the user's scores of it.
FRANCHISE_SHARE = 0.65
# Community recommendations of loved shows: points per point the loved show's score is above
# the user's average, at most RECOMMENDED_CAP.
RECOMMENDED_WEIGHT = 0.3
RECOMMENDED_CAP = 2.0
# A show recommended by one the user scored at least this far above their average.
LOVED_ABOVE_MEAN = 1.0
# GUILTY WATCH: MAL's score below this (and below the user's usual by GUILTY_MAL_MARGIN), yet
# at least GUILTY_TOP_MATCHES of the user's most watched categories and a liking for it.
GUILTY_MAL_MAX = 7.0
GUILTY_MAL_MARGIN = 0.5
GUILTY_TOP_TAGS = 6
GUILTY_TOP_MATCHES = 2
GUILTY_MIN_TASTE = 0.3


@dataclass(frozen=True)
class Show:
    """The parts of a show the model and the statistics look at."""

    id: int
    title: str
    mean: float | None = None
    tags: tuple[tuple[int, str], ...] = ()
    studios: tuple[str, ...] = ()
    source: str | None = None
    media_type: str | None = None
    year: int | None = None
    members: int | None = None
    rank: int | None = None
    duration_s: int | None = None
    num_episodes: int | None = None
    picture_url: str | None = None
    title_en: str | None = None

    @classmethod
    def of(cls, anime: Anime) -> "Show":
        # Shows cached before the genre ids were stored only have the names.
        tags = anime.genre_tags or tags_from_names(anime.genres or [])
        year = anime.start_year
        if year is None and anime.start_season and anime.start_season[-4:].isdigit():
            year = int(anime.start_season[-4:])
        return cls(
            id=anime.id,
            title=anime.title,
            mean=anime.mean,
            tags=tuple((t["id"], t["name"]) for t in tags),
            studios=tuple(anime.studios or ()),
            source=anime.source,
            media_type=anime.media_type,
            year=year,
            members=anime.num_list_users,
            rank=anime.rank,
            duration_s=anime.average_episode_duration,
            num_episodes=anime.num_episodes,
            picture_url=anime.picture_url,
            title_en=anime.title_en,
        )


@dataclass(frozen=True)
class Rated:
    """A show on the user's list: its status and the user's score (0 = not scored)."""

    show: Show
    status: str
    score: int = 0
    episodes_watched: int = 0


@lru_cache(maxsize=20_000)
def features(show: Show) -> dict[str, str]:
    """The show's one-hot features, each with a readable name. (Cached: fitting looks at each
    show many times. The result must not be modified.)"""
    out: dict[str, str] = {}
    for tag_id, name in show.tags:
        out[f"tag:{tag_id}"] = name
    for studio in show.studios[:MAX_STUDIOS]:
        out[f"studio:{studio}"] = studio
    if show.source:
        out[f"source:{show.source}"] = f"{show.source.replace('_', ' ').capitalize()} source"
    if show.media_type:
        out[f"type:{show.media_type}"] = _media_label(show.media_type)
    if show.year:
        decade = show.year // 10 * 10
        out[f"era:{decade}"] = f"{decade}s"
    return out


def _media_label(media_type: str) -> str:
    labels = {"tv": "TV", "ova": "OVA", "ona": "ONA", "tv_special": "TV special"}
    return labels.get(media_type, media_type.replace("_", " ").capitalize())


def feature_kind(key: str) -> str:
    """genre / theme / demographic / explicit for tags, else the key's prefix (studio, ...)."""
    prefix, _, value = key.partition(":")
    return category(int(value)) if prefix == "tag" else prefix


def _popularity(show: Show) -> float | None:
    return math.log10(show.members + 1) if show.members else None


@dataclass
class Prediction:
    score: float
    tier: Tier
    # The features that moved it most, as (feature key, name, points), strongest first. The key
    # ("tag:62", "source:manga", "mal", "popularity", "franchise", "recommended", ...) lets the
    # UI translate the name.
    reasons: list[tuple[str, str, float]] = field(default_factory=list)
    # Rated low by the community, but it's what the user watches most (and likes).
    guilty: bool = False


# The user's scored shows a show is related to: (title, the user's score).
Related = list[tuple[str, int]]


@dataclass
class Context:
    """What the regression can't see, for one user (see predictor_for)."""

    # The user's scored shows: anime id -> (title, score)
    scored: dict[int, tuple[str, int]] = field(default_factory=dict)

    # anime id -> the user's scored shows of the same franchise (prequel, sequel, ...)
    franchise: dict[int, Related] = field(default_factory=dict)
    # anime id -> the shows the user scored highly whose community recommendations include it
    recommended: dict[int, Related] = field(default_factory=dict)


def _strongest(related: Related, mean: float) -> str:
    """How the related show felt most strongly is named: "Season 1 (★10)"."""
    title, score = max(related, key=lambda r: abs(r[1] - mean))
    return f"{title} (★{score})"


def _average(related: Related) -> float:
    return sum(score for _, score in related) / len(related)


def link_franchise(context: Context, anime_id: int, relations: list[dict[str, Any]]) -> None:
    """A show's own relations (see related.py): the ones the user scored count for it."""
    found = context.franchise.setdefault(anime_id, [])
    for entry in relations:
        other = context.scored.get(entry["row"]["id"])
        if other is not None and other not in found:
            found.append(other)
    if not found:
        del context.franchise[anime_id]


class Predictor:
    """A fitted model (the dict stored in TasteModel.data), with the user's Context."""

    def __init__(self, data: dict[str, Any], context: Context | None = None):
        self.data = data
        self.weights: dict[str, float] = data["weights"]
        self.names: dict[str, str] = dict(data["names"])  # (gets the related shows' titles)
        self.context = context or Context()
        self.top_tags: set[str] = set(data.get("top_tags", []))

    def _terms(self, show: Show) -> tuple[float, list[tuple[str, float]]]:
        d = self.data
        terms: list[tuple[str, float]] = []
        mal = (show.mean - d["mal_center"]) if show.mean is not None else 0.0
        terms.append(("mal", d["mal_coef"] * mal))
        pop = _popularity(show)
        if pop is not None and pop > d["pop_center"]:
            # Being very popular can help a show; being little known never counts against it.
            terms.append(("popularity", max(0.0, d["pop_coef"] * (pop - d["pop_center"]))))
        for key in features(show):
            if key in self.weights:
                terms.append((key, self.weights[key]))
        mean = d.get("user_mean", 7.0)
        if recommended := self.context.recommended.get(show.id):
            points = RECOMMENDED_WEIGHT * (_average(recommended) - mean)
            self.names[f"recommended:{show.id}"] = _strongest(recommended, mean)
            terms.append(
                (f"recommended:{show.id}", max(-RECOMMENDED_CAP, min(RECOMMENDED_CAP, points)))
            )
        if franchise := self.context.franchise.get(show.id):
            # Towards the user's own scores of the franchise, from what the rest predicts.
            base = d["intercept"] + sum(v for _, v in terms)
            self.names[f"franchise:{show.id}"] = _strongest(franchise, mean)
            terms.append((f"franchise:{show.id}", FRANCHISE_SHARE * (_average(franchise) - base)))
        return d["intercept"] + sum(v for _, v in terms), terms

    def name(self, key: str) -> str:
        return {"mal": "MAL score", "popularity": "Popularity"}.get(key) or self.names[key]

    def guilty_limit(self) -> float:
        """Below this MAL score a show can be a guilty pleasure."""
        return min(GUILTY_MAL_MAX, self.data["mal_center"] - GUILTY_MAL_MARGIN)

    def guilty(self, show: Show, terms: list[tuple[str, float]]) -> bool:
        """The community rates it low, yet it's in the categories the user watches most and
        their taste (everything but MAL's score and popularity) likes it."""
        if show.mean is None or not self.top_tags:
            return False
        if show.mean >= self.guilty_limit():
            return False
        matches = sum(1 for key in features(show) if key in self.top_tags)
        taste = sum(v for key, v in terms if key not in ("mal", "popularity"))
        return matches >= GUILTY_TOP_MATCHES and taste >= GUILTY_MIN_TASTE

    def score(self, show: Show) -> float:
        return round(min(10.0, max(1.0, self._terms(show)[0])), 2)

    def tier(self, score: float) -> Tier:
        for tier, threshold in zip(TIERS, self.data["thresholds"], strict=False):
            if score >= threshold:
                return tier
        return TIERS[-1]

    def predict(self, show: Show, reasons: int = 0) -> Prediction:
        raw, terms = self._terms(show)
        score = round(min(10.0, max(1.0, raw)), 2)
        # The franchise first whenever it counts (the user scored it themselves).
        strongest = sorted(
            terms, key=lambda t: (t[0].startswith("franchise:"), abs(t[1])), reverse=True
        )
        return Prediction(
            score=score,
            tier=self.tier(score),
            reasons=[
                # franchise:<id> / recommended:<id> -> franchise / recommended (the name is
                # the related show's title)
                (
                    key.split(":")[0] if key.startswith(("franchise:", "recommended:")) else key,
                    self.name(key),
                    round(v, 2),
                )
                for key, v in strongest[:reasons]
                if abs(v) >= 0.05
            ],  # fmt: skip
            guilty=self.guilty(show, terms),
        )


def _training_rows(rated: list[Rated]) -> tuple[list[Show], np.ndarray, np.ndarray]:
    scored = [r for r in rated if r.score > 0]
    shows = [r.show for r in scored]
    y = [float(r.score) for r in scored]
    w = [1.0] * len(scored)
    if scored:
        # A show dropped without a score counts as one of the user's low scores.
        low = min(float(np.percentile(y, 20)), float(np.mean(y)) - 1.5)
        for r in rated:
            if r.score == 0 and r.status == ListStatus.dropped:
                shows.append(r.show)
                y.append(max(1.0, low))
                w.append(DROPPED_WEIGHT)
    return shows, np.array(y), np.array(w)


def _design(
    shows: list[Show], vocab: list[str], mal_center: float, pop_center: float
) -> np.ndarray:
    index = {key: i for i, key in enumerate(vocab)}
    x = np.zeros((len(shows), 3 + len(vocab)))
    for row, show in enumerate(shows):
        x[row, 0] = 1.0
        x[row, 1] = (show.mean - mal_center) if show.mean is not None else 0.0
        pop = _popularity(show)
        x[row, 2] = (pop - pop_center) if pop is not None else 0.0
        for key in features(show):
            if key in index:
                x[row, 3 + index[key]] = 1.0
    return x


def _solve(x: np.ndarray, y: np.ndarray, w: np.ndarray, n_onehot: int) -> np.ndarray:
    ridge_mal = RIDGE_MAL_PER_SHOW * len(y)
    penalty = np.diag([0.0, ridge_mal, RIDGE_POPULARITY] + [RIDGE] * n_onehot)
    xtw = x.T * w
    return np.linalg.solve(xtw @ x + penalty, xtw @ y)


def _fit_arrays(shows: list[Show], y: np.ndarray, w: np.ndarray) -> dict[str, Any]:
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for show in shows:
        for key, name in features(show).items():
            counts[key] = counts.get(key, 0) + 1
            names[key] = name
    vocab = sorted(k for k, c in counts.items() if c >= MIN_FEATURE_COUNT)
    means = [s.mean for s in shows if s.mean is not None]
    pops = [p for s in shows if (p := _popularity(s)) is not None]
    mal_center = float(np.mean(means)) if means else 7.0
    pop_center = float(np.mean(pops)) if pops else 5.0
    coef = _solve(_design(shows, vocab, mal_center, pop_center), y, w, len(vocab))
    return {
        "intercept": float(coef[0]),
        "mal_coef": float(coef[1]),
        "mal_center": mal_center,
        "pop_coef": float(coef[2]),
        "pop_center": pop_center,
        "weights": {k: float(v) for k, v in zip(vocab, coef[3:], strict=True)},
        "names": {k: names[k] for k in vocab},
        "counts": {k: counts[k] for k in vocab},
    }


def fit(rated: list[Rated]) -> dict[str, Any] | None:
    """Fit a user's model, or None when they have scored too few shows."""
    shows, y, w = _training_rows(rated)
    if int((w == 1.0).sum()) < MIN_SCORED:
        return None
    model = _fit_arrays(shows, y, w)
    scores = y[w == 1.0]

    # Cross-validated predictions: how well the model does on shows it didn't see, and the
    # spread of predictions the tiers are cut from.
    order = np.random.default_rng(0).permutation(len(shows))
    cv = np.zeros(len(shows))
    folds = FOLDS if len(shows) >= 4 * FOLDS else 1
    for fold in range(folds):
        test = order[fold::folds] if folds > 1 else order
        train = np.setdiff1d(order, test) if folds > 1 else order
        part = Predictor(_fit_arrays([shows[i] for i in train], y[train], w[train]))
        for i in test:
            cv[i] = part.score(shows[i])
    model["thresholds"] = [float(np.percentile(cv, p)) for p in TIER_PERCENTILES]

    real = w == 1.0
    user_mean = float(scores.mean())
    # The baseline to beat: MAL's score, shifted by how much higher or lower the user scores.
    community = [s.mean for s, r in zip(shows, real, strict=True) if r and s.mean is not None]
    offset = user_mean - float(np.mean(community)) if community else 0.0
    baseline = np.array([(s.mean + offset) if s.mean is not None else user_mean for s in shows])
    model.update(
        top_tags=_top_tags(rated),
        version=MODEL_VERSION,
        n=int(real.sum()),
        user_mean=user_mean,
        user_std=float(scores.std()),
        mae=float(np.abs(cv - y)[real].mean()) if folds > 1 else None,
        baseline_mae=float(np.abs(baseline - y)[real].mean()),
    )
    return model


def _top_tags(rated: list[Rated]) -> list[str]:
    """The categories (genres, themes, demographics) the user watches most: on the most shows
    they watched (not dropped, not just planned)."""
    counts: dict[str, int] = {}
    for r in rated:
        if r.status in (ListStatus.plan_to_watch, ListStatus.dropped):
            continue
        for tag_id, _ in r.show.tags:
            counts[f"tag:{tag_id}"] = counts.get(f"tag:{tag_id}", 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:GUILTY_TOP_TAGS]]


async def load_rated(db: AsyncSession, user_id: int) -> list[Rated]:
    rows = await db.execute(
        select(ListEntry, Anime)
        .join(Anime, Anime.id == ListEntry.anime_id)
        .where(ListEntry.user_id == user_id)
    )
    return [
        Rated(Show.of(anime), entry.status, entry.score, entry.episodes_watched)
        for entry, anime in rows.all()
    ]


async def refit(db: AsyncSession, user: User, rated: list[Rated] | None = None) -> Predictor | None:
    """Fit and store the user's model (on sync); None when there's too little to go on."""
    data = fit(rated if rated is not None else await load_rated(db, user.id))
    row = await db.get(TasteModel, user.id)
    if row is None:
        row = TasteModel(user_id=user.id)
        db.add(row)
    # Too few scores is stored too, so it isn't refitted on every page view.
    row.data = data or {"version": MODEL_VERSION, "insufficient": True}
    row.fitted_at = datetime.now(UTC)
    return Predictor(data) if data else None


async def load_context(db: AsyncSession, user_id: int, mean: float) -> Context:
    """The user's scored shows' franchises (AniList relations, cached; missing ones are fetched
    in the background) and the community recommendations of the ones they loved."""
    from app.services import related

    rows = await db.execute(
        select(ListEntry.anime_id, ListEntry.score, Anime.title, Anime.title_en)
        .join(Anime, Anime.id == ListEntry.anime_id)
        .where(ListEntry.user_id == user_id, ListEntry.score > 0)
    )
    scored = {anime_id: (title_en or title, score) for anime_id, score, title, title_en in rows}
    context = Context(scored=scored)
    relations = await related.cached(list(scored))
    # One step further too (season 1 counts for season 3): the relations of the related shows.
    near = {e["row"]["id"]: e for found in relations.values() for e in found}
    further = await related.cached([i for i in near if i not in scored])
    related.ensure(
        user_id,
        [i for i in scored if i not in relations]
        + [i for i in near if i not in scored and i not in further],
    )
    for anime_id, found in relations.items():
        for entry in found:
            link = entry["row"]["id"]
            if scored[anime_id] not in context.franchise.setdefault(link, []):
                context.franchise[link].append(scored[anime_id])
            for second in further.get(link, []):
                target = second["row"]["id"]
                if target != anime_id and target not in scored:
                    franchise = context.franchise.setdefault(target, [])
                    if scored[anime_id] not in franchise:
                        franchise.append(scored[anime_id])
    loved = [i for i, (_, score) in scored.items() if score >= mean + LOVED_ABOVE_MEAN]
    if loved:
        recs = await db.scalars(
            select(CommunityRecommendation).where(CommunityRecommendation.anime_id.in_(loved))
        )
        for rec in recs:
            context.recommended.setdefault(rec.recommended_id, []).append(scored[rec.anime_id])
    return context


async def predictor_for(db: AsyncSession, user: User | None) -> Predictor | None:
    """The user's stored model (fitted first if it's missing or older than their list), with
    their context (see load_context)."""
    predictor = await _fitted(db, user)
    if predictor is not None and user is not None:
        predictor.context = await load_context(db, user.id, predictor.data.get("user_mean", 7.0))
    return predictor


async def _fitted(db: AsyncSession, user: User | None) -> Predictor | None:
    if user is None:
        return None
    row = await db.get(TasteModel, user.id)
    stale = row is None or row.data.get("version") != MODEL_VERSION
    if not stale and user.last_synced_at is not None:
        stale = row.fitted_at < user.last_synced_at
    if not stale:
        return None if row.data.get("insufficient") else Predictor(row.data)
    if user.last_synced_at is None:
        return None  # nothing synced yet
    predictor = await refit(db, user)
    await db.commit()
    return predictor
