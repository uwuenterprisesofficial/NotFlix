"""Statistics about a user's MyAnimeList list, compared with MAL's community scores."""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.models import ListStatus
from app.services.taste import Predictor, Rated, Show, feature_kind, features

DEFAULT_EPISODE_S = 24 * 60
AFFINITY_PRIOR = 3  # shows of "no opinion" every tag's average is pulled towards
DROPPED_AFFINITY = -1.5  # a dropped show without a score, in points below the user's mean
MIN_FAVOURITE_COUNT = 3
FAVOURITES = 8
HOT_TAKE_GAP = 1.5  # points between the user's score and MAL's for a show to be a hot take
HIDDEN_GEM_MEMBERS = 100_000
TAG_KINDS = ("genre", "theme", "demographic", "explicit")
OTHER_KINDS = ("studio", "source", "type", "era")
PER_KIND_LIMIT = {"theme": 40, "studio": 25}


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None or math.isnan(value) else round(float(value), digits)


def _mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def show_ref(show: Show, score: int = 0, predictor: Predictor | None = None) -> dict[str, Any]:
    prediction = None
    if predictor is not None and score == 0:
        p = predictor.predict(show)
        prediction = {"score": p.score, "tier": p.tier, "reasons": []}
    return {
        "id": show.id,
        "title": show.title,
        "title_en": show.title_en,
        "picture_url": show.picture_url,
        "mean": show.mean,
        "score": score or None,
        "prediction": prediction,
    }


@dataclass
class _Bucket:
    name: str
    kind: str
    count: int = 0
    dropped: int = 0
    scores: list[float] = field(default_factory=list)
    pairs: list[tuple[float, float]] = field(default_factory=list)  # (user score, MAL mean)
    affinity_sum: float = 0.0
    affinity_n: int = 0


def _overview(rated: list[Rated]) -> dict[str, Any]:
    by_status = defaultdict(int)
    for r in rated:
        by_status[r.status] += 1
    scored = [r for r in rated if r.score > 0]
    scores = [r.score for r in scored]
    pairs = [(r.score, r.show.mean) for r in scored if r.show.mean is not None]
    episodes = sum(r.episodes_watched for r in rated)
    seconds = sum(r.episodes_watched * (r.show.duration_s or DEFAULT_EPISODE_S) for r in rated)
    members = [r.show.members for r in rated if r.show.members]
    agreement = None
    if len(pairs) >= 5:
        mine, mal = np.array(pairs).T
        if mine.std() > 0 and mal.std() > 0:
            agreement = float(np.corrcoef(mine, mal)[0, 1])
    finished = by_status[ListStatus.completed] + by_status[ListStatus.dropped]
    return {
        "total": len(rated),
        "by_status": [
            {"status": s.value, "count": by_status[s.value]}
            for s in ListStatus
            if by_status[s.value]
        ],
        "episodes": episodes,
        "days": _round(seconds / 86400, 1),
        "scored": len(scored),
        "mean_score": _round(_mean(scores)),
        "median_score": _round(float(np.median(scores))) if scores else None,
        "std_score": _round(float(np.std(scores))) if scores else None,
        # MAL's community mean of the same shows the user scored: what "average" would say.
        "mal_mean": _round(_mean([m for _, m in pairs])),
        "mean_difference": _round(_mean([s - m for s, m in pairs])),
        "mean_abs_difference": _round(_mean([abs(s - m) for s, m in pairs])),
        "agreement": _round(agreement),
        "median_members": int(np.median(members)) if members else None,
        "drop_rate": _round(by_status[ListStatus.dropped] / finished) if finished else None,
    }


def _distribution(rated: list[Rated]) -> list[dict[str, int]]:
    mine = defaultdict(int)
    mal = defaultdict(int)
    for r in rated:
        if r.score > 0:
            mine[r.score] += 1
            if r.show.mean is not None:
                mal[min(10, max(1, round(r.show.mean)))] += 1
    return [{"score": s, "mine": mine[s], "mal": mal[s]} for s in range(1, 11)]


def _buckets(rated: list[Rated], user_mean: float) -> dict[str, _Bucket]:
    buckets: dict[str, _Bucket] = {}
    for r in rated:
        for key, name in features(r.show).items():
            b = buckets.get(key)
            if b is None:
                b = buckets[key] = _Bucket(name=name, kind=feature_kind(key))
            b.count += 1
            if r.status == ListStatus.dropped:
                b.dropped += 1
            if r.score > 0:
                b.scores.append(r.score)
                b.affinity_sum += r.score - user_mean
                b.affinity_n += 1
                if r.show.mean is not None:
                    b.pairs.append((r.score, r.show.mean))
            elif r.status == ListStatus.dropped:
                b.affinity_sum += DROPPED_AFFINITY
                b.affinity_n += 1
    return buckets


def _tag_stat(key: str, b: _Bucket, total: int, predictor: Predictor | None) -> dict[str, Any]:
    delta = _mean([s - m for s, m in b.pairs])
    return {
        "key": key,
        "name": b.name,
        "kind": b.kind,
        "count": b.count,
        "share": _round(b.count / total, 3),
        "scored": len(b.scores),
        "mean_score": _round(_mean(b.scores)),
        "mal_mean": _round(_mean([m for _, m in b.pairs])),
        "delta": _round(delta),
        # The average points above/below the user's own mean, pulled towards 0 for few shows.
        "affinity": _round(b.affinity_sum / (b.affinity_n + AFFINITY_PRIOR)),
        "weight": _round(predictor.weights.get(key)) if predictor else None,
        "dropped": b.dropped,
    }


def _hot_takes(
    rated: list[Rated], stats: dict[str, dict[str, Any]], overview: dict[str, Any]
) -> list[dict[str, Any]]:
    takes: list[dict[str, Any]] = []
    scored = [r for r in rated if r.score > 0 and r.show.mean is not None]

    offset = overview["mean_difference"]
    if offset is not None and abs(offset) >= 0.3:
        harsher = offset < 0
        takes.append(
            {
                "kind": "harsh" if harsher else "generous",
                "title": "Tough critic" if harsher else "Easy to please",
                "text": (
                    f"You score {abs(offset):.1f} points {'lower' if harsher else 'higher'} than "
                    f"MAL does on the same shows ({overview['mean_score']:.2f} vs "
                    f"{overview['mal_mean']:.2f})."
                ),
                "value": offset,
            }
        )

    agreement = overview["agreement"]
    if agreement is not None:
        if agreement < 0.3:
            title, text = "Contrarian", "Your scores barely follow MAL's"
        elif agreement > 0.7:
            title, text = "In tune with MAL", "Your scores closely follow MAL's"
        else:
            title, text = "Own opinion", "You mostly agree with MAL, with your own twists"
        takes.append(
            {
                "kind": "agreement",
                "title": title,
                "text": f"{text} (correlation {agreement:.2f}).",
                "value": agreement,
            }
        )

    underrated = sorted(
        (r for r in scored if r.score - r.show.mean >= HOT_TAKE_GAP),
        key=lambda r: r.score - r.show.mean,
        reverse=True,
    )
    for r in underrated[:4]:
        takes.append(
            {
                "kind": "underrated",
                "title": "You love it, MAL doesn't",
                "text": f"You gave it a {r.score} — MAL's average is {r.show.mean:.2f}.",
                "value": round(r.score - r.show.mean, 2),
                "anime": show_ref(r.show, r.score),
            }
        )

    overrated = sorted(
        (r for r in scored if r.show.mean - r.score >= HOT_TAKE_GAP),
        key=lambda r: r.show.mean - r.score,
        reverse=True,
    )
    for r in overrated[:4]:
        rank = f"#{r.show.rank} on MAL, " if r.show.rank and r.show.rank <= 500 else ""
        takes.append(
            {
                "kind": "overrated",
                "title": "Overrated, says you",
                "text": f"{rank}{r.show.mean:.2f} average — you gave it a {r.score}.",
                "value": round(r.score - r.show.mean, 2),
                "anime": show_ref(r.show, r.score),
            }
        )

    dropped = sorted(
        (
            r
            for r in rated
            if r.status == ListStatus.dropped and r.show.mean is not None and r.show.mean >= 8
        ),
        key=lambda r: r.show.mean,
        reverse=True,
    )
    for r in dropped[:3]:
        takes.append(
            {
                "kind": "dropped_acclaimed",
                "title": "Dropped a classic",
                "text": f"You dropped it after {r.episodes_watched} episode(s), "
                f"despite its {r.show.mean:.2f} on MAL.",
                "value": r.show.mean,
                "anime": show_ref(r.show, r.score),
            }
        )

    gems = sorted(
        (
            r
            for r in rated
            if r.score >= 8 and r.show.members and r.show.members < HIDDEN_GEM_MEMBERS
        ),
        key=lambda r: (-r.score, r.show.members),
    )
    for r in gems[:3]:
        takes.append(
            {
                "kind": "hidden_gem",
                "title": "Hidden gem",
                "text": f"You gave it a {r.score}; only {r.show.members:,} MAL users have it "
                "on their list.",
                "value": float(r.score),
                "anime": show_ref(r.show, r.score),
            }
        )

    # Genres/themes the user scores differently from MAL, beyond their usual offset.
    base = offset or 0.0
    contrarian = [
        s
        for s in stats.values()
        if s["kind"] in ("genre", "theme", "demographic")
        and s["delta"] is not None
        and s["scored"] >= 4
        and abs(s["delta"] - base) >= 0.5
    ]
    contrarian.sort(key=lambda s: abs(s["delta"] - base), reverse=True)
    for s in contrarian[:4]:
        diff = s["delta"] - base
        takes.append(
            {
                "kind": "tag_contrarian",
                "title": f"{s['name']}: {'soft spot' if diff > 0 else 'not impressed'}",
                "text": (
                    f"You rate {s['name']} {abs(diff):.1f} points "
                    f"{'more generously' if diff > 0 else 'more harshly'} than MAL, "
                    f"compared with your usual ({s['scored']} scored shows)."
                ),
                "value": round(diff, 2),
            }
        )
    for take in takes:
        take.setdefault("anime", None)
    return takes


def _model_stats(predictor: Predictor | None) -> dict[str, Any] | None:
    if predictor is None:
        return None
    d = predictor.data
    ranked = sorted(predictor.weights.items(), key=lambda kv: kv[1], reverse=True)

    def item(key: str, weight: float) -> dict[str, Any]:
        return {"name": predictor.names[key], "kind": feature_kind(key), "points": round(weight, 2)}

    return {
        "scored": d["n"],
        "mae": _round(d["mae"]),
        "baseline_mae": _round(d["baseline_mae"]),
        "mal_weight": _round(d["mal_coef"]),
        "thresholds": [round(t, 2) for t in d["thresholds"]],
        "likes": [item(k, w) for k, w in ranked[:10] if w > 0.05],
        "dislikes": [item(k, w) for k, w in reversed(ranked[-10:]) if w < -0.05],
    }


def compute(rated: list[Rated], predictor: Predictor | None) -> dict[str, Any]:
    overview = _overview(rated)
    user_mean = overview["mean_score"] or 7.0
    buckets = _buckets(rated, user_mean)
    stats = {key: _tag_stat(key, b, len(rated), predictor) for key, b in buckets.items()}

    by_kind: dict[str, list[dict[str, Any]]] = {k: [] for k in (*TAG_KINDS, *OTHER_KINDS)}
    for s in stats.values():
        by_kind.setdefault(s["kind"], []).append(s)
    for kind, items in by_kind.items():
        if kind == "era":
            items.sort(key=lambda s: s["key"])
        else:
            items.sort(key=lambda s: (-s["count"], s["name"]))
        if kind in PER_KIND_LIMIT:
            del items[PER_KIND_LIMIT[kind] :]

    tags = [
        s
        for s in stats.values()
        if s["kind"] in ("genre", "theme", "demographic")
        and s["count"] >= MIN_FAVOURITE_COUNT
        and s["affinity"] is not None
    ]
    favourites = sorted((s for s in tags if s["affinity"] > 0), key=lambda s: -s["affinity"])
    hated = sorted((s for s in tags if s["affinity"] < 0), key=lambda s: s["affinity"])

    plan = [r for r in rated if r.status == ListStatus.plan_to_watch]
    if predictor is not None:
        plan.sort(key=lambda r: predictor.score(r.show), reverse=True)
    else:
        plan.sort(key=lambda r: r.show.mean or 0, reverse=True)

    return {
        "overview": overview,
        "score_distribution": _distribution(rated),
        "favourites": favourites[:FAVOURITES],
        "hated": hated[:FAVOURITES],
        "breakdown": by_kind,
        "hot_takes": _hot_takes(rated, stats, overview),
        "model": _model_stats(predictor),
        "plan_to_watch": [show_ref(r.show, r.score, predictor) for r in plan[:12]],
    }
