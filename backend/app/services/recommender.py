"""Personal recommendations from a user's MyAnimeList list.

1. Build a genre taste profile: shows scored above the user's own mean pull their genres up,
   shows below it (and dropped shows) pull them down.
2. Collect candidates from MAL's community recommendations of the user's best-rated shows.
3. Rank candidates by genre affinity, community vote strength and MAL mean score.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field

from app.models import ListStatus

IMPLICIT_WEIGHT = {
    ListStatus.completed: 0.5,
    ListStatus.watching: 0.5,
    ListStatus.plan_to_watch: 0.25,
    ListStatus.on_hold: 0.0,
    ListStatus.dropped: -1.0,
}
W_GENRE, W_SOCIAL, W_QUALITY = 0.5, 0.3, 0.2


@dataclass(frozen=True)
class ListItem:
    anime_id: int
    title: str
    genres: list[str]
    status: str
    score: int  # 0 = unscored


@dataclass
class Candidate:
    anime_id: int
    genres: list[str] = field(default_factory=list)
    mean: float | None = None
    votes: int = 0  # summed MAL "num_recommendations" across seeds
    seeds: list[int] = field(default_factory=list)  # list anime that recommended this one


@dataclass(frozen=True)
class Ranked:
    anime_id: int
    score: float
    reason: str | None


def taste_profile(items: list[ListItem]) -> dict[str, float]:
    scores = [i.score for i in items if i.score > 0]
    user_mean = sum(scores) / len(scores) if scores else 7.0

    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        if item.score > 0:
            weight = item.score - user_mean
        else:
            weight = IMPLICIT_WEIGHT.get(ListStatus(item.status), 0.0)
        for genre in item.genres:
            totals[genre] += weight
            counts[genre] += 1

    # Dividing by sqrt(count) keeps very common genres (Action, Comedy) from dominating.
    profile = {g: totals[g] / math.sqrt(counts[g]) for g in totals}
    peak = max((abs(v) for v in profile.values()), default=0.0)
    return {g: v / peak for g, v in profile.items()} if peak else profile


def seed_shows(items: list[ListItem], limit: int = 15) -> list[ListItem]:
    """The shows whose community recommendations are worth exploring."""
    liked = [i for i in items if i.status != ListStatus.dropped]
    return sorted(liked, key=lambda i: (i.score, i.status == ListStatus.completed), reverse=True)[
        :limit
    ]


def score_candidate(profile: dict[str, float], c: Candidate) -> float:
    affinity = sum(profile.get(g, 0.0) for g in c.genres) / len(c.genres) if c.genres else 0.0
    social = min(1.0, math.log1p(c.votes) / math.log1p(50))
    quality = max(-1.0, min(1.0, ((c.mean or 7.0) - 7.0) / 2.0))
    return W_GENRE * affinity + W_SOCIAL * social + W_QUALITY * quality


def rank(items: list[ListItem], candidates: list[Candidate], limit: int = 30) -> list[Ranked]:
    profile = taste_profile(items)
    on_list = {i.anime_id for i in items}
    titles = {i.anime_id: i.title for i in items}

    ranked = []
    for c in candidates:
        if c.anime_id in on_list:
            continue
        seed = next((titles[s] for s in c.seeds if s in titles), None)
        ranked.append(
            Ranked(
                anime_id=c.anime_id,
                score=round(score_candidate(profile, c), 4),
                reason=f"Because you liked {seed}" if seed else None,
            )
        )
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked[:limit]
