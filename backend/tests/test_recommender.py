from app.services.recommender import Candidate, ListItem, rank, seed_shows, taste_profile


def _item(anime_id, genres, status="completed", score=0, title=None):
    return ListItem(anime_id, title or f"Show {anime_id}", genres, status, score)


LIST = [
    _item(1, ["Action", "Sci-Fi"], score=10, title="Steins;Gate"),
    _item(2, ["Sci-Fi", "Drama"], score=9),
    _item(3, ["Romance", "Comedy"], score=4),
    _item(4, ["Sports"], status="dropped"),
    _item(5, ["Mystery"], status="plan_to_watch"),
]


def test_taste_profile_follows_scores_relative_to_user_mean():
    profile = taste_profile(LIST)
    assert profile["Sci-Fi"] == max(profile.values())
    assert profile["Romance"] == -1.0  # the strongest opinion, liked or disliked, maps to +-1
    assert profile["Sports"] < 0
    assert profile["Mystery"] > 0


def test_seed_shows_prefers_high_scores_and_skips_dropped():
    seeds = seed_shows(LIST, limit=2)
    assert [s.anime_id for s in seeds] == [1, 2]
    assert all(s.status != "dropped" for s in seed_shows(LIST))


def test_rank_excludes_listed_and_prefers_matching_genres():
    candidates = [
        Candidate(anime_id=1, genres=["Sci-Fi"], mean=9.0, votes=100, seeds=[2]),
        Candidate(anime_id=10, genres=["Sci-Fi", "Action"], mean=8.0, votes=10, seeds=[1]),
        Candidate(anime_id=11, genres=["Romance"], mean=8.0, votes=10, seeds=[2]),
    ]
    ranked = rank(LIST, candidates)
    assert [r.anime_id for r in ranked] == [10, 11]
    assert ranked[0].reason == "Because you liked Steins;Gate"


def test_rank_handles_empty_list():
    ranked = rank([], [Candidate(anime_id=1, genres=["Action"], mean=8.5, votes=3)])
    assert len(ranked) == 1
    assert ranked[0].reason is None


def test_rank_uses_the_predicted_score_over_genres_when_there_is_one():
    candidates = [
        Candidate(anime_id=10, genres=["Sci-Fi"], mean=8.0, votes=10, seeds=[1], predicted=5.0),
        Candidate(anime_id=11, genres=["Romance"], mean=8.0, votes=10, seeds=[1], predicted=9.5),
    ]
    assert [r.anime_id for r in rank(LIST, candidates)] == [11, 10]
