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
    assert reasons[0] == ("tag:62", "Isekai", pytest.approx(predictor.weights["tag:62"], abs=0.01))


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

    from app.services import stats_jobs

    await stats_jobs.forget(user.id)
    first = (await client.get("/me/stats")).json()
    assert first["status"] == "loading" and first["stats"] is None
    await stats_jobs.wait_idle()
    resp = await client.get("/me/stats")
    assert resp.status_code == 200
    ready = resp.json()
    assert ready["status"] == "ready"
    body = ready["stats"]
    assert body["overview"]["scored"] == 60
    assert body["model"]["scored"] == 60
    assert body["plan_to_watch"][0]["prediction"]["tier"] in ("skip", "avoid")

    detail = (await client.get("/anime/900")).json()
    assert detail["prediction"]["tier"] in ("must_watch", "recommended")
    assert detail["prediction"]["reasons"][0]["key"] == "tag:40"
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


def test_shows_cached_before_genre_ids_use_their_genre_names():
    from app.models import Anime

    anime = Anime(
        id=1, title="Old", genres=["Action", "Isekai", "Shounen", "Romantic Subtext", "Unknown"],
        genre_tags=[], start_season="fall 2019",
    )  # fmt: skip
    show = Show.of(anime)
    assert show.tags == ((1, "Action"), (62, "Isekai"), (27, "Shounen"), (74, "Romantic Subtext"))
    assert show.year == 2019


async def test_stats_fill_in_missing_show_details_from_mal(client, user, monkeypatch):
    """Shows without genre ids/members get their details fetched in the background."""
    from app.core.config import get_settings
    from app.db.session import sync_session
    from app.models import Anime
    from app.services import mal, stats_jobs
    from app.services.stats_jobs import redis

    listed = [(r.show, r.status, r.score) for r in _list(20)]
    _seed_list(user, listed)
    with sync_session() as db:
        for anime in db.query(Anime).all():
            anime.genre_tags, anime.num_list_users, anime.studios = [], None, []
        db.commit()
    for show, _, _ in listed:
        await redis().delete(f"anime:details-tried:{show.id}")

    detail_calls = []

    def node(show):
        return {
            "id": show.id, "title": show.title, "mean": show.mean,
            "genres": [{"id": i, "name": n} for i, n in show.tags],
            "studios": [{"id": 1, "name": show.studios[0]}], "num_list_users": show.members,
        }  # fmt: skip

    async def my_animelist(self):
        # The list endpoint leaves some shows incomplete; those are fetched one by one.
        return [{"node": {**node(s), "num_list_users": None} if s.id % 2 else node(s),
                 "list_status": {}} for s, _, _ in listed]  # fmt: skip

    async def anime(self, anime_id, extra_fields=""):
        detail_calls.append(anime_id)
        return node(next(s for s, _, _ in listed if s.id == anime_id))

    monkeypatch.setattr(get_settings(), "mal_client_id", "id")
    monkeypatch.setattr(mal.MalClient, "my_animelist", my_animelist)
    monkeypatch.setattr(mal.MalClient, "anime", anime)
    await stats_jobs.forget(user.id)

    assert (await client.get("/me/stats")).json()["status"] == "loading"
    await stats_jobs.wait_idle()
    body = (await client.get("/me/stats")).json()
    assert body["status"] == "ready"
    assert sorted(detail_calls) == sorted(s.id for s, _, _ in listed if s.id % 2)
    assert len(body["stats"]["breakdown"]["genre"]) >= 4
    with sync_session() as db:
        assert all(a.genre_tags and a.num_list_users for a in db.query(Anime).all())


async def test_stats_in_an_old_format_are_not_shown(client, user):
    from app.core.cache import set_json
    from app.services import stats_jobs

    _seed_list(user, [(r.show, r.status, r.score) for r in _list(20)])
    old = {"version": "1:whenever", "computed_at": "2026-01-01T00:00:00+00:00", "stats": {"x": 1}}
    await set_json(f"stats:{user.id}", old, 60)
    body = (await client.get("/me/stats")).json()
    assert body["status"] == "loading" and body["stats"] is None
    await stats_jobs.wait_idle()
    assert (await client.get("/me/stats")).json()["status"] == "ready"


def test_personal_taste_outweighs_mals_score():
    # A user who agrees with MAL exactly: the model still leans less on MAL than that.
    rng = random.Random(3)
    rated = []
    for i in range(120):
        show = _show(rng, i)
        rated.append(Rated(show, "completed", round(min(10, max(1, show.mean + 0.5)))))
    model = fit(rated)
    assert 0.2 < model["mal_coef"] < 0.75


def test_franchise_and_community_recommendations_move_the_prediction():
    from app.services.taste import FRANCHISE_WEIGHT, RECOMMENDED_WEIGHT, Context

    model = fit(_list())
    mean = model["user_mean"]
    rng = random.Random(9)
    sequel = _show(rng, 500, tags=[(1, "Action"), (4, "Comedy"), (27, "Shounen")])
    plain = Predictor(model).predict(sequel, reasons=10)
    context = Context(
        franchise={500: [("Season 1", 10)]},
        recommended={500: [("A favourite", 10), ("Another", 9)]},
    )
    boosted = Predictor(model, context).predict(sequel, reasons=10)
    expected = FRANCHISE_WEIGHT * (10 - mean) + RECOMMENDED_WEIGHT * (9.5 - mean)
    assert boosted.score == pytest.approx(min(10, plain.score + expected), abs=0.02)
    reasons = {key: name for key, name, _ in boosted.reasons}
    assert reasons["franchise"] == "Season 1"
    assert reasons["recommended"] == "A favourite"
    # A franchise the user disliked pulls it down.
    disliked = Predictor(model, Context(franchise={500: [("Season 1", 3)]})).predict(sequel)
    assert disliked.score < plain.score


def test_guilty_watch_low_mal_score_in_the_users_favourite_categories():
    model = fit(_list())
    rng = random.Random(4)
    predictor = Predictor(model)
    names = dict(TAGS)
    # Psychological (loved), with two of the categories the user watches most.
    top = sorted(int(t[4:]) for t in predictor.top_tags if t not in ("tag:40", "tag:62"))[:2]
    favourites = [(40, "Psychological"), *((t, names[t]) for t in top)]
    trashy = _show(rng, 600, tags=favourites, mean=5.9)
    assert predictor.predict(trashy).guilty is True
    # Rated well by the community: just a good match, not a guilty one.
    assert predictor.predict(_show(rng, 601, tags=favourites, mean=8.4)).guilty is False
    # Low and not the user's thing: no label either.
    isekai = _show(rng, 602, tags=[(62, "Isekai"), (36, "Slice of Life")], mean=5.9)
    assert predictor.predict(isekai).guilty is False


async def test_the_context_comes_from_relations_and_community_recommendations(database, user):
    import json

    from sqlalchemy import delete

    from app.core.cache import close, redis
    from app.db.session import AsyncSessionLocal, async_engine, sync_session
    from app.models import Anime, CommunityRecommendation, ListEntry
    from app.services.taste import load_context

    with sync_session() as db:
        db.execute(delete(ListEntry).where(ListEntry.user_id == user.id))
        db.execute(delete(CommunityRecommendation))
        db.execute(delete(Anime).where(Anime.id.in_([701, 702, 703])))
        db.add(Anime(id=701, title="Loved S1", genres=[]))
        db.add(Anime(id=702, title="Meh", genres=[]))
        db.add(ListEntry(user_id=user.id, anime_id=701, status="completed", score=10))
        db.add(ListEntry(user_id=user.id, anime_id=702, status="completed", score=6))
        db.add_all(
            CommunityRecommendation(anime_id=a, recommended_id=r, votes=5,
                                    fetched_at=datetime.now(UTC))
            for a, r in ((701, 800), (702, 801))
        )  # fmt: skip
        db.commit()
    await redis().set(
        "related:701", json.dumps([{"relation": "SEQUEL", "row": {"id": 703, "title": "S2"}}])
    )
    await redis().set("related:702", json.dumps([]))
    async with AsyncSessionLocal() as db:
        context = await load_context(db, user.id, mean=8.0)
    assert context.franchise == {703: [("Loved S1", 10)]}
    # Only what fans of the loved show recommend.
    assert context.recommended == {800: [("Loved S1", 10)]}
    await async_engine.dispose()
    await close()
