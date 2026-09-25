import random
from datetime import UTC, datetime

import pytest

from app.services import jikan, stats
from app.services.taste import MIN_SCORED, Predictor, Rated, Show, feature_kind, features, fit

pytestmark = pytest.mark.anyio

TAGS = [
    (1, "Action"),
    (4, "Comedy"),
    (22, "Romance"),
    (40, "Psychological"),
    (62, "Isekai"),
    (27, "Shounen"),
    (42, "Seinen"),
    (36, "Slice of Life"),
]
TASTE = {40: 1.5, 62: -2.0}  # loves Psychological, hates Isekai


def _show(rng: random.Random, anime_id: int, tags=None, mean=None, members=None) -> Show:
    return Show(
        id=anime_id,
        title=f"Show {anime_id}",
        mean=mean if mean is not None else round(rng.uniform(6, 9), 2),
        tags=tuple(tags or rng.sample(TAGS, 3)),
        studios=(rng.choice(["Madhouse", "MAPPA", "A-1 Pictures"]),),
        source="manga",
        media_type="tv",
        year=rng.randint(1995, 2024),
        members=members or rng.randint(10_000, 3_000_000),
    )


def _list(n: int = 200, seed: int = 1) -> list[Rated]:
    rng = random.Random(seed)
    rated = []
    for i in range(n):
        show = _show(rng, i)
        score = 7 + 0.8 * (show.mean - 7.5) + sum(TASTE.get(t, 0) for t, _ in show.tags)
        score = round(min(10, max(1, score + rng.gauss(0, 0.7))))
        rated.append(Rated(show, "completed", score))
    return rated


def test_features_are_grouped_by_mal_id():
    show = Show(1, "x", tags=((1, "Action"), (9, "Ecchi"), (27, "Shounen"), (62, "Isekai")))
    kinds = {features(show)[k]: feature_kind(k) for k in features(show)}
    assert kinds == {
        "Action": "genre",
        "Ecchi": "explicit",
        "Shounen": "demographic",
        "Isekai": "theme",
    }


def test_model_learns_liked_and_hated_themes():
    model = fit(_list())
    weights = model["weights"]
    assert weights["tag:40"] > 1.0
    assert weights["tag:62"] < -1.5
    assert abs(weights["tag:1"]) < 0.5
    # Better than MAL's score alone on shows it didn't see.
    assert model["mae"] < model["baseline_mae"] * 0.7
    assert model["thresholds"] == sorted(model["thresholds"], reverse=True)


def test_predictions_are_labelled_from_the_users_own_range():
    predictor = Predictor(fit(_list()))
    rng = random.Random(5)
    loved = _show(rng, 1000, tags=[(40, "Psychological"), (42, "Seinen")], mean=8.8)
    hated = _show(rng, 1001, tags=[(62, "Isekai"), (27, "Shounen")], mean=6.5)
    assert predictor.predict(loved).tier == "must_watch"
    assert predictor.predict(hated).tier == "avoid"
    reasons = predictor.predict(hated, reasons=3).reasons
    assert reasons[0] == ("Isekai", pytest.approx(predictor.weights["tag:62"], abs=0.01))


def test_no_model_without_enough_scores():
    rated = _list(MIN_SCORED - 1)
    assert fit(rated) is None
    # Unscored shows don't count.
    assert fit([Rated(r.show, "completed", 0) for r in _list(50)]) is None


def test_stats_find_favourites_hot_takes_and_rank_plan_to_watch():
    rated = _list()
    rng = random.Random(9)
    classic = _show(rng, 500, tags=[(62, "Isekai")], mean=8.9)
    gem = _show(rng, 501, tags=[(40, "Psychological")], mean=6.2, members=5_000)
    rated += [
        Rated(classic, "dropped", 0, episodes_watched=2),
        Rated(gem, "completed", 10),
        Rated(_show(rng, 502, tags=[(40, "Psychological")], mean=8.0), "plan_to_watch"),
        Rated(_show(rng, 503, tags=[(62, "Isekai")], mean=8.0), "plan_to_watch"),
    ]
    result = stats.compute(rated, Predictor(fit(rated)))

    assert result["favourites"][0]["name"] == "Psychological"
    assert result["hated"][0]["name"] == "Isekai"
    assert result["overview"]["total"] == len(rated)
    assert sum(b["mine"] for b in result["score_distribution"]) == result["overview"]["scored"]
    kinds = {t["kind"] for t in result["hot_takes"]}
    assert {"dropped_acclaimed", "hidden_gem", "underrated", "agreement"} <= kinds
    gem_take = next(t for t in result["hot_takes"] if t["kind"] == "hidden_gem")
    assert gem_take["anime"]["id"] == 501
    assert [s["id"] for s in result["plan_to_watch"]] == [502, 503]
    assert result["plan_to_watch"][0]["prediction"]["score"] > 8
    assert result["model"]["likes"][0]["name"] == "Psychological"
    assert {s["name"] for s in result["breakdown"]["demographic"]} == {"Shounen", "Seinen"}


def test_stats_without_scores():
    rng = random.Random(1)
    result = stats.compute([Rated(_show(rng, 1), "plan_to_watch")], None)
    assert result["overview"]["mean_score"] is None
    assert result["model"] is None
    assert result["hot_takes"] == []


def test_jikan_rows_match_mal_columns():
    row = jikan.anime_row(
        {
            "mal_id": 5114,
            "title": "Fullmetal Alchemist: Brotherhood",
            "title_english": "Fullmetal Alchemist: Brotherhood",
            "images": {"jpg": {"large_image_url": "https://cdn/x.jpg"}},
            "type": "TV",
            "status": "Finished Airing",
            "episodes": 64,
            "score": 9.1,
            "members": 3_500_000,
            "rank": 1,
            "genres": [{"mal_id": 1, "name": "Action"}],
            "themes": [{"mal_id": 38, "name": "Military"}],
            "demographics": [{"mal_id": 27, "name": "Shounen"}],
            "studios": [{"mal_id": 4, "name": "Bones"}],
            "source": "Manga",
            "rating": "R - 17+ (violence & profanity)",
            "duration": "24 min per ep",
            "season": "spring",
            "year": 2009,
        }
    )
    assert row["media_type"] == "tv"
    assert row["status"] == "finished_airing"
    assert row["rating"] == "r"
    assert row["average_episode_duration"] == 24 * 60
    assert row["genre_tags"] == [
        {"id": 1, "name": "Action"},
        {"id": 38, "name": "Military"},
        {"id": 27, "name": "Shounen"},
    ]
    assert row["start_season"] == "spring 2009"
    assert jikan._duration_s("1 hr 55 min") == 115 * 60


def _seed_list(user, entries):
    from sqlalchemy import delete

    from app.db.session import sync_session
    from app.models import Anime, ListEntry, TasteModel, User

    with sync_session() as db:
        db.execute(delete(ListEntry))
        db.execute(delete(TasteModel))
        db.execute(delete(Anime))
        for show, _, _ in entries:
            db.add(
                Anime(
                    id=show.id,
                    title=show.title,
                    mean=show.mean,
                    genres=[n for _, n in show.tags],
                    genre_tags=[{"id": i, "name": n} for i, n in show.tags],
                    studios=list(show.studios),
                    num_list_users=show.members,
                    media_type="tv",
                )
            )
        db.flush()
        for show, status, score in entries:
            db.add(ListEntry(user_id=user.id, anime_id=show.id, status=status, score=score))
        synced = datetime.now(UTC)
        db.get(User, user.id).last_synced_at = synced
        db.commit()
    user.last_synced_at = synced


async def test_stats_and_predictions_in_the_api(client, user):
    rng = random.Random(3)
    listed = [(r.show, r.status, r.score) for r in _list(60)]
    unlisted = _show(rng, 900, tags=[(40, "Psychological")], mean=8.5)
    plan = _show(rng, 901, tags=[(62, "Isekai")], mean=7.0)
    _seed_list(user, [*listed, (plan, "plan_to_watch", 0)])
    from app.db.session import sync_session
    from app.models import Anime

    with sync_session() as db:
        db.add(Anime(id=unlisted.id, title="Unlisted Mind Game", mean=8.5, genres=["Psychological"],
                     genre_tags=[{"id": 40, "name": "Psychological"}]))  # fmt: skip
        db.commit()

    resp = await client.get("/me/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overview"]["scored"] == 60
    assert body["model"]["scored"] == 60
    assert body["plan_to_watch"][0]["prediction"]["tier"] in ("skip", "avoid")

    detail = (await client.get("/anime/900")).json()
    assert detail["prediction"]["tier"] in ("must_watch", "recommended")
    assert detail["prediction"]["reasons"][0]["name"] == "Psychological"
    assert detail["tags"] == [{"id": 40, "name": "Psychological", "category": "theme"}]
    # Scored shows get no prediction.
    assert (await client.get(f"/anime/{listed[0][0].id}")).json()["prediction"] is None

    found = (await client.get("/search", params={"q": "mind game"})).json()
    assert found["source"] == "local"
    assert [a["id"] for a in found["items"]] == [900]
    assert found["items"][0]["prediction"] is not None

    genre = (await client.get("/search/genre/40", params={"order": "score"})).json()
    assert genre["source"] == "local"
    ids = [a["id"] for a in genre["items"]]
    assert 900 in ids and 901 not in ids
    assert all("Psychological" in a["genres"] for a in genre["items"])
    means = [a["mean"] for a in genre["items"]]
    assert means == sorted(means, reverse=True)


async def test_genre_list_falls_back_to_known_tags(client):
    genres = (await client.get("/genres")).json()
    by_id = {g["id"]: g for g in genres}
    assert by_id[1]["category"] == "genre"
    assert by_id[9]["category"] == "explicit"
    assert by_id[27]["category"] == "demographic"
    assert by_id[62]["category"] == "theme"
    assert genres[0]["category"] == "genre"
    assert genres[-1]["category"] == "explicit"


async def test_stats_need_sign_in(client):
    assert (await client.get("/me/stats")).status_code == 401
