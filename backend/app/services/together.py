"""Watch Together: what two connected users should watch, from both of their lists.

Each user's taste is their score predictor (services.taste), or without one (too few scores)
their genre profile plus MAL's score. A show's appeal to a user is how far above their own
average it's predicted, in their own spread of scores (a z-score), so a generous and a strict
scorer count the same.

- **Together** (new to both): shows neither has on their list, ranked by a blend of the
  lower and the average of the two appeals ("least misery": both should like it).
- **Continue together**: shows both are watching (or put on hold).
- **Planned**: shows both planned, or one planned and the other would like.
- **Show this to <name>**: shows one loved (well above their average) that the other hasn't
  seen but would like, per their taste.
- **You both loved**: common ground.

The compatibility score combines how alike the two score shows both have seen (correlation)
with how alike their genre tastes are (cosine of the genre profiles).

A guest (no account), or someone whose list is empty, has no taste to go on: only the other's
list is used, with the show's general appeal (MAL score and popularity) standing in for the
missing side. Without any list, the rows are the catalogue's best rated and most popular shows.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_json, redis, set_json
from app.models import Anime, Connection, ListStatus, Recommendation, User
from app.services import recommender
from app.services.tags import EXPLICIT_GENRE_IDS
from app.services.taste import Predictor, Rated, Show, load_rated, predictor_for

FORMAT = 2  # bump when the cached result's shape changes
CACHE_TTL_S = 24 * 3600
POOL_SIZE = 2500  # the catalogue's most popular shows are candidates, besides both users' recs
ROW_SIZE = 24
MIN_STD = 0.75  # a user who scores everything alike still has some spread
LOVED_Z = 0.5  # a score this many standard deviations above the user's average is "loved"
LOVED_MIN = 7
LOVED_ALWAYS = 9
MIN_BOTH_SCORED = 5  # fewer shows scored by both: compatibility from genres alone
SEEN = {ListStatus.watching, ListStatus.completed, ListStatus.on_hold, ListStatus.dropped}


@dataclass
class Member:
    user_id: int
    rated: dict[int, Rated]
    predictor: Predictor | None
    mean: float
    std: float
    profile: dict[str, float]

    def status(self, anime_id: int) -> str | None:
        r = self.rated.get(anime_id)
        return r.status if r else None

    def score(self, anime_id: int) -> int:
        r = self.rated.get(anime_id)
        return r.score if r else 0

    def appeal(self, show: Show) -> tuple[float, float | None]:
        """How much the user would like the show (z-score), and their predicted score."""
        if self.predictor is not None:
            predicted = self.predictor.score(show)
            return (predicted - self.mean) / self.std, predicted
        names = [name for _, name in show.tags]
        genres = sum(self.profile.get(n, 0.0) for n in names) / len(names) if names else 0.0
        quality = ((show.mean or 7.0) - 7.0) / 1.5
        return 0.6 * genres + 0.4 * quality, None

    def love(self, anime_id: int) -> float | None:
        """How far above their average the user scored it, when that makes it a favourite."""
        score = self.score(anime_id)
        if score < LOVED_MIN:
            return None
        z = (score - self.mean) / self.std
        # A 9 or 10 is a favourite even for a generous scorer.
        return max(z, LOVED_Z) if z >= LOVED_Z or score >= LOVED_ALWAYS else None


def member(user_id: int, rated: list[Rated], predictor: Predictor | None) -> Member:
    scores = [r.score for r in rated if r.score > 0]
    items = [
        recommender.ListItem(
            r.show.id, r.show.title, [n for _, n in r.show.tags], r.status, r.score
        )
        for r in rated
    ]
    return Member(
        user_id=user_id,
        rated={r.show.id: r for r in rated},
        predictor=predictor,
        mean=float(np.mean(scores)) if scores else 7.0,
        std=max(float(np.std(scores)) if scores else 0.0, MIN_STD),
        profile=recommender.taste_profile(items),
    )


def general(show: Show) -> float:
    """How good a show is for anyone: MAL's score, a little popularity (a z-score-like scale)."""
    quality = ((show.mean or 7.0) - 7.5) / 0.75
    popularity = math.log10(show.members + 1) - 5 if show.members else -1.0
    return quality + 0.25 * popularity


def _joint(za: float, zb: float) -> float:
    return 0.6 * min(za, zb) + 0.4 * (za + zb) / 2


def _explicit(show: Show) -> bool:
    return any(tag_id in EXPLICIT_GENRE_IDS for tag_id, _ in show.tags)


def _pair(a: Member | None, b: Member | None, show: Show) -> dict[str, Any]:
    """Both users' side of a show: their status and score, else their predicted score (None for
    a side without a list)."""
    out: dict[str, Any] = {}
    for side, m in (("a", a), ("b", b)):
        if m is None:
            out[side] = None
            continue
        z, predicted = m.appeal(show)
        out[side] = {
            "status": m.status(show.id),
            "score": m.score(show.id) or None,
            "predicted": predicted if not m.score(show.id) else None,
            "appeal": round(z, 3),
        }
    return out


NO_COMPATIBILITY = {
    "score": None, "correlation": None, "genre_similarity": None, "shared": 0,
    "both_scored": 0, "shared_genres": [], "disagreements": [],
}  # fmt: skip


def compatibility(a: Member | None, b: Member | None) -> dict[str, Any]:
    if a is None or b is None:
        return dict(NO_COMPATIBILITY)
    shared = [i for i in a.rated if a.status(i) in SEEN and b.status(i) in SEEN]
    both_scored = [i for i in shared if a.score(i) and b.score(i)]
    correlation = None
    if len(both_scored) >= MIN_BOTH_SCORED:
        xs = np.array([a.score(i) for i in both_scored], dtype=float)
        ys = np.array([b.score(i) for i in both_scored], dtype=float)
        if xs.std() > 0 and ys.std() > 0:
            correlation = float(np.corrcoef(xs, ys)[0, 1])

    genres = sorted(set(a.profile) | set(b.profile))
    va = np.array([a.profile.get(g, 0.0) for g in genres])
    vb = np.array([b.profile.get(g, 0.0) for g in genres])
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
    cosine = float(va @ vb / norm) if norm else None

    parts = []
    if correlation is not None:
        parts.append((0.6, (correlation + 1) / 2))
    if cosine is not None:
        parts.append((0.4 if parts else 1.0, (cosine + 1) / 2))
    score = round(100 * sum(w * v for w, v in parts) / sum(w for w, _ in parts)) if parts else None

    # Genres both like / only one of them likes, strongest first.
    liked = sorted(
        (g for g in genres if a.profile.get(g, 0) > 0.15 and b.profile.get(g, 0) > 0.15),
        key=lambda g: -min(a.profile[g], b.profile[g]),
    )
    differences = sorted(both_scored, key=lambda i: abs(a.score(i) - b.score(i)), reverse=True)
    return {
        "score": score,
        "correlation": round(correlation, 3) if correlation is not None else None,
        "genre_similarity": round(cosine, 3) if cosine is not None else None,
        "shared": len(shared),
        "both_scored": len(both_scored),
        "shared_genres": liked[:6],
        # Shows they disagree on most (at least 3 points apart).
        "disagreements": [i for i in differences if abs(a.score(i) - b.score(i)) >= 3][:8],
    }


def _top(scored: list[tuple[int, float]]) -> list[int]:
    return [i for i, _ in sorted(scored, key=lambda s: -s[1])[:ROW_SIZE]]


def build(a: Member | None, b: Member | None, pool: dict[int, Show]) -> dict[str, list[int]]:
    """The rows (sides "a" and "b"): {row id: [anime ids]}, from both lists, one, or none."""
    if a is not None and b is not None:
        return _build_both(a, b, pool)
    if a is not None or b is not None:
        return _build_one(a or b, "b" if a is not None else "a", pool)
    return _build_none(pool)


def _build_one(m: Member, other: str, pool: dict[int, Show]) -> dict[str, list[int]]:
    """Only one of them has a list: their taste, with general appeal for the other."""
    shows = dict(pool) | {i: r.show for i, r in m.rated.items()}
    together, continuing, planned, favourites = [], [], [], []
    for i, show in shows.items():
        if _explicit(show):
            continue
        status = m.status(i)
        if status is None:
            joint = 0.6 * m.appeal(show)[0] + 0.4 * general(show)
            if joint > 0 and show.media_type != "music":
                together.append((i, joint))
        elif status in (ListStatus.watching, ListStatus.on_hold):
            continuing.append((i, m.appeal(show)[0]))
        elif status == ListStatus.plan_to_watch:
            planned.append((i, m.appeal(show)[0]))
        if (love := m.love(i)) is not None:
            favourites.append((i, 0.7 * love + 0.3 * general(show)))
    return {
        "together": _top(together),
        "continue": _top(continuing),
        "planned": _top(planned),
        f"show_to_{other}": _top(favourites),
    }


def _build_none(pool: dict[int, Show]) -> dict[str, list[int]]:
    """Nobody has a list: what's good and popular in the catalogue."""
    shows = [s for s in pool.values() if not _explicit(s) and s.media_type != "music"]
    return {
        "top_rated": _top([(s.id, general(s)) for s in shows if s.mean]),
        "popular": _top([(s.id, float(s.members or 0)) for s in shows]),
    }


def _build_both(a: Member, b: Member, pool: dict[int, Show]) -> dict[str, list[int]]:
    """The rows for a pair with both lists."""
    shows = dict(pool)
    for m in (a, b):
        shows.update({i: r.show for i, r in m.rated.items()})

    def appeal(i: int) -> tuple[float, float]:
        return a.appeal(shows[i])[0], b.appeal(shows[i])[0]

    together, planned, continuing, loved = [], [], [], []
    for i, show in shows.items():
        if _explicit(show):
            continue
        sa, sb = a.status(i), b.status(i)
        if sa is None and sb is None:
            za, zb = appeal(i)
            joint = _joint(za, zb)
            if joint > 0 and show.media_type != "music":
                together.append((i, joint))
        elif {sa, sb} <= {ListStatus.watching, ListStatus.on_hold}:
            continuing.append((i, _joint(*appeal(i))))
        elif ListStatus.plan_to_watch in (sa, sb) and {sa, sb} <= {ListStatus.plan_to_watch, None}:
            za, zb = appeal(i)
            # One planned it: only when the other would like it too.
            if (sa == sb) or min(za, zb) > 0.3:
                planned.append((i, _joint(za, zb) + (0.5 if sa == sb else 0)))
        la, lb = a.love(i), b.love(i)
        if la is not None and lb is not None:
            loved.append((i, la + lb))

    def show_to(giver: Member, getter: Member) -> list[int]:
        """The giver's favourites the getter hasn't seen and would like."""
        out = []
        for i in giver.rated:
            love = giver.love(i)
            if love is None or getter.status(i) in SEEN or _explicit(shows[i]):
                continue
            z = getter.appeal(shows[i])[0]
            if z > -0.5:
                out.append((i, 0.5 * love + 0.5 * z))
        return _top(out)

    return {
        "together": _top(together),
        "continue": _top(continuing),
        "planned": _top(planned),
        "show_to_b": show_to(a, b),
        "show_to_a": show_to(b, a),
        "both_loved": _top(loved),
    }


async def _pool(db: AsyncSession, user_ids: tuple[int, int]) -> dict[int, Show]:
    popular = select(Anime).where(
        Anime.num_list_users.is_not(None),
        or_(Anime.status.is_(None), Anime.status != "not_yet_aired"),
    )
    found = {
        a.id: Show.of(a)
        for a in await db.scalars(popular.order_by(Anime.num_list_users.desc()).limit(POOL_SIZE))
    }
    recs = select(Anime).join(Recommendation, Recommendation.anime_id == Anime.id)
    for a in await db.scalars(recs.where(Recommendation.user_id.in_(user_ids))):
        found.setdefault(a.id, Show.of(a))
    return found


async def cached(connection_id: int) -> dict[str, Any] | None:
    return await get_json(f"together:{connection_id}")


async def forget(connection_id: int) -> None:
    await redis().delete(f"together:{connection_id}")


def _version(a: User, b: User) -> str:
    stamp = [
        "guest" if u.is_guest else u.last_synced_at.isoformat() if u.last_synced_at else "never"
        for u in (a, b)
    ]
    return f"{FORMAT}:{stamp[0]}:{stamp[1]}"


async def _member(db: AsyncSession, user: User) -> Member | None:
    """The user's taste; None for a guest or an empty list."""
    if user.is_guest:
        return None
    rated = await load_rated(db, user.id)
    return member(user.id, rated, await predictor_for(db, user)) if rated else None


async def report(db: AsyncSession, connection_id: int, a: User, b: User) -> dict[str, Any]:
    """The pair's rows, compatibility and each shown show's scores for both, cached until either
    list is synced again. Sides "a" and "b" are the connection's users (lower id first)."""
    key = f"together:{connection_id}"
    cached = await get_json(key)
    if cached is not None and cached.get("version") == _version(a, b):
        return cached

    ma, mb = await _member(db, a), await _member(db, b)
    pool = await _pool(db, (a.id, b.id))
    rows = build(ma, mb, pool)
    compat = compatibility(ma, mb)
    shows = dict(pool)
    for m in (ma, mb):
        if m is not None:
            shows.update({i: r.show for i, r in m.rated.items()})
    ids = {i for row in rows.values() for i in row} | set(compat["disagreements"])
    result = {
        "version": _version(a, b),
        "computed_at": datetime.now().astimezone().isoformat(),
        "rows": rows,
        "lists": {"a": ma is not None, "b": mb is not None},
        "compatibility": compat,
        "pairs": {str(i): _pair(ma, mb, shows[i]) for i in ids},
    }
    await set_json(key, result, CACHE_TTL_S)
    return result


def for_viewer(pair: dict[str, Any], viewer_is_a: bool) -> dict[str, Any]:
    me, partner = ("a", "b") if viewer_is_a else ("b", "a")
    return {"me": pair[me], "partner": pair[partner]}


async def absorb_guest(db: AsyncSession, guest: User, user: User) -> None:
    """A guest signed in with an account that already has a user: the guest's connections move
    to that user (unless it's connected with that person already), and the guest goes."""
    found = await db.scalars(
        select(Connection).where(
            or_(Connection.user_a_id == guest.id, Connection.user_b_id == guest.id)
        )
    )
    for conn in list(found):
        partner = conn.partner_of(guest.id)
        a, b = sorted((user.id, partner))
        duplicate = partner == user.id or await db.scalar(
            select(Connection.id).where(Connection.user_a_id == a, Connection.user_b_id == b)
        )
        if duplicate:
            await db.delete(conn)
        else:
            conn.user_a_id, conn.user_b_id = a, b
    await db.flush()
    await db.delete(guest)
