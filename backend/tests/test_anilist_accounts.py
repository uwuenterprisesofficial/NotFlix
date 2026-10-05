from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import delete, select

from app.db.session import sync_session
from app.models import Anime, ListEntry, Recommendation, TasteModel, User
from app.services import anilist_account, list_writer, mal

pytestmark = pytest.mark.anyio


def _media(mal_id, title, genres=("Action",), score=80):
    return {
        "id": mal_id + 1000, "idMal": mal_id, "episodes": 12, "format": "TV",
        "status": "FINISHED", "averageScore": score, "popularity": 5000, "duration": 24,
        "source": "MANGA", "title": {"romaji": title, "english": None},
        "coverImage": {"large": None}, "description": f"{title} (AniList)", "genres": list(genres),
        "season": "SPRING", "seasonYear": 2020, "startDate": {"year": 2020},
        "studios": {"nodes": [{"name": "Bones"}]},
    }  # fmt: skip


def _al_entry(mal_id, title, status="COMPLETED", score=8, progress=12):
    return {
        "status": status, "score": score, "progress": progress, "updatedAt": 1_700_000_000,
        "media": _media(mal_id, title),
    }  # fmt: skip


def _mal_entry(mal_id, title, status="completed", score=9, episodes=12):
    return {
        "node": {"id": mal_id, "title": title, "genres": [{"id": 1, "name": "Action"}],
                 "mean": 8.0, "num_episodes": 12},
        "list_status": {"status": status, "score": score, "num_episodes_watched": episodes},
    }  # fmt: skip


@pytest.fixture
def clean(database):
    with sync_session() as db:
        for model in (ListEntry, Recommendation, TasteModel, Anime):
            db.execute(delete(model))
        db.commit()


def _set_user(user, **fields):
    with sync_session() as db:
        row = db.get(User, user.id)
        for key, value in fields.items():
            setattr(row, key, value)
            setattr(user, key, value)
        db.commit()


class FakeAniList:
    """Stands in for AniListClient; records writes."""

    entries: list = []
    saved: list = []

    def __init__(self, token=None, http=None):
        self.token = token

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def animelist(self, user_id):
        return FakeAniList.entries

    async def ids_for(self, mal_ids):
        return {i: i + 1000 for i in mal_ids}

    async def save_entry(self, media_id, status, progress=None, score=None):
        FakeAniList.saved.append((media_id, status, progress, score))
        return {"id": 1, "status": status, "progress": progress}


def test_anilist_entries_map_onto_mal_ids():
    entries, skipped = anilist_account.parse_entries(
        [
            _al_entry(5, "Five", status="REPEATING"),
            _al_entry(6, "Six", status="PLANNING", score=0, progress=0),
            {"status": "COMPLETED", "media": {"id": 1, "idMal": None}},
        ]
    )
    assert skipped == 1
    assert [(e.mal_id, e.status, e.score) for e in entries] == [
        (5, "watching", 8),
        (6, "plan_to_watch", 0),
    ]
    row = anilist_account.anime_row(_media(5, "Five", genres=("Action", "Romance")))
    assert row["mean"] == 8.0 and row["media_type"] == "tv" and row.get("num_list_users") is None
    assert row["genre_tags"] == [{"id": 1, "name": "Action"}, {"id": 22, "name": "Romance"}]


async def test_sync_with_anilist_only(client, user, clean, monkeypatch):
    _set_user(user, mal_user_id=None, access_token=None, anilist_user_id=77,
              anilist_token="al", anilist_name="al-user")  # fmt: skip
    FakeAniList.entries = [_al_entry(5, "Five"), _al_entry(6, "Six", status="CURRENT")]
    monkeypatch.setattr(anilist_account, "AniListClient", FakeAniList)

    body = (await client.post("/me/sync")).json()
    assert body["entries"] == 2 and body["adding_to_mal"] == 0
    with sync_session() as db:
        entries = {e.anime_id: e.status for e in db.scalars(select(ListEntry))}
        assert entries == {5: "completed", 6: "watching"}
        assert db.get(Anime, 5).synopsis == "Five (AniList)"
    me = (await client.get("/me")).json()
    assert me["mal"] is None and me["anilist"] == {"name": "al-user"}


async def test_sync_with_both_completes_each_list(client, user, clean, monkeypatch):
    _set_user(user, anilist_user_id=77, anilist_token="al", anilist_name="al-user")
    FakeAniList.entries = [_al_entry(5, "Five"), _al_entry(6, "Six", status="PAUSED", score=0)]
    FakeAniList.saved = []
    added_to_mal = []

    async def my_animelist(self):
        return [_mal_entry(5, "Five", score=10), _mal_entry(7, "Seven", status="dropped")]

    async def update(self, anime_id, **fields):
        added_to_mal.append((anime_id, fields))
        return {}

    monkeypatch.setattr(anilist_account, "AniListClient", FakeAniList)
    monkeypatch.setattr(list_writer.anilist_account, "AniListClient", FakeAniList)
    monkeypatch.setattr(list_writer, "ANILIST_PAUSE_S", 0)
    monkeypatch.setattr(mal.MalClient, "my_animelist", my_animelist)
    monkeypatch.setattr(mal.MalClient, "update_my_list_status", update)

    body = (await client.post("/me/sync")).json()
    assert (body["entries"], body["adding_to_mal"], body["adding_to_anilist"]) == (3, 1, 1)
    await list_writer.wait_idle()
    # Only what the other list lacked is added, with its status, progress and score.
    assert added_to_mal == [(6, {"status": "on_hold", "num_watched_episodes": 12})]
    assert FakeAniList.saved == [(1007, "dropped", 12, 9)]
    with sync_session() as db:
        scores = {e.anime_id: e.score for e in db.scalars(select(ListEntry))}
    assert scores == {5: 10, 6: 0, 7: 9}  # both have 5: MAL's entry counts


async def test_progress_is_written_to_both_lists(client, user, clean, monkeypatch):
    from app.services import anilist

    _set_user(user, anilist_user_id=77, anilist_token="al", anilist_name="al-user")
    with sync_session() as db:
        db.add(Anime(id=5, title="Five", num_episodes=12, genres=[]))
        db.commit()
    FakeAniList.saved = []
    monkeypatch.setattr(anilist_account, "AniListClient", FakeAniList)

    async def anilist_id(mal_id):
        return mal_id + 1000

    async def update(self, anime_id, **fields):
        raise mal.MalError("MAL down")

    monkeypatch.setattr(anilist, "anilist_id", anilist_id)
    monkeypatch.setattr(mal.MalClient, "update_my_list_status", update)
    body = (await client.put("/anime/5/progress", json={"episodes_watched": 3})).json()
    assert body["episodes_watched"] == 3 and body["failed"] == ["mal"]
    assert FakeAniList.saved == [(1005, "watching", 3, None)]


@pytest.fixture
def providers(monkeypatch, clean):
    """Both sign-ins configured, with MAL and AniList's OAuth and profile calls faked."""
    from app.api import auth
    from app.api.deps import current_user_optional
    from app.core.config import get_settings
    from app.main import app

    settings = get_settings()
    for key, value in (("mal_client_id", "m"), ("anilist_client_id", "a"),
                       ("anilist_client_secret", "s")):  # fmt: skip
        monkeypatch.setattr(settings, key, value)
    app.dependency_overrides.pop(current_user_optional, None)  # real sessions
    with sync_session() as db:
        db.execute(delete(User))
        db.commit()

    async def mal_exchange(code, verifier):
        return mal.TokenSet({"access_token": "mt", "refresh_token": "mr", "expires_in": 3600})

    async def mal_me(self):
        return {"id": 11, "name": "mal-user", "picture": "mal-pic"}

    async def al_exchange(code):
        return anilist_account.Token("at", datetime(2100, 1, 1, tzinfo=UTC))

    class Viewer(FakeAniList):
        async def viewer(self):
            return {"id": 22, "name": "al-user", "avatar": {"large": "al-pic"}}

    monkeypatch.setattr(auth.mal, "exchange_code", mal_exchange)
    monkeypatch.setattr(auth.mal.MalClient, "me", mal_me)
    monkeypatch.setattr(auth.anilist_account, "exchange_code", al_exchange)
    monkeypatch.setattr(auth.anilist_account, "AniListClient", Viewer)
    # Signing in syncs the list in the background: recorded here instead (no MAL in tests).
    synced: list[int] = []
    monkeypatch.setattr(auth.sync_jobs, "start", synced.append)
    return synced


def _state(location: str) -> str:
    from urllib.parse import parse_qs, urlsplit

    return parse_qs(urlsplit(location).query)["state"][0]


async def _sign_in(client, provider, **params):
    """Start a login and complete its callback; returns the callback's redirect."""
    start = await client.get("/auth/login", params={"provider": provider, **params})
    assert start.status_code == 307
    callback = "/auth/callback" if provider == "mal" else "/auth/anilist/callback"
    done = await client.get(
        callback, params={"code": "c", "state": _state(start.headers["location"])}
    )
    return done.headers["location"]


async def test_sign_in_with_both_links_them_to_one_user(client, providers):
    after_mal = await _sign_in(client, "mal", then="anilist")
    # MAL done: on to AniList, linked to the user just signed in.
    assert after_mal.endswith("/api/auth/login?provider=anilist&link=true")
    start = await client.get("/auth/login", params={"provider": "anilist", "link": "true"})
    done = await client.get(
        "/auth/anilist/callback", params={"code": "c", "state": _state(start.headers["location"])}
    )
    assert done.headers["location"].endswith("/settings?login=ok&account=anilist")
    me = (await client.get("/me")).json()
    assert (me["name"], me["mal"], me["anilist"]) == (
        "mal-user", {"name": "mal-user"}, {"name": "al-user"},
    )  # fmt: skip
    with sync_session() as db:
        assert db.scalar(select(User.id).where(User.anilist_user_id == 22)) == me["id"]


async def test_linking_takes_the_account_from_another_user(client, providers):
    # Someone signed in with AniList alone first...
    await _sign_in(client, "anilist")
    alone = (await client.get("/me")).json()
    assert alone["mal"] is None
    await client.post("/auth/logout")
    # ...then with MAL, and links that AniList account in Settings.
    await _sign_in(client, "mal")
    location = await _sign_in(client, "anilist", link="true")
    assert "/settings?" in location
    me = (await client.get("/me")).json()
    assert me["id"] != alone["id"] and me["anilist"] == {"name": "al-user"}
    with sync_session() as db:
        assert db.get(User, alone["id"]) is None  # nothing left on the old user

    # Either list can be removed, but not the last one.
    assert (await client.delete("/auth/accounts/anilist")).status_code == 204
    assert (await client.delete("/auth/accounts/mal")).status_code == 409
    assert (await client.get("/me")).json()["anilist"] is None


async def test_providers_and_unconfigured_login(client):
    providers = (await client.get("/auth/providers")).json()
    assert providers == {
        "mal": False,
        "anilist": False,
        "public_url": "http://localhost:3000",
        "redirects": {
            "mal": "http://localhost:3000/api/auth/callback",
            "anilist": "http://localhost:3000/api/auth/anilist/callback",
        },
    }
    resp = await client.get("/auth/login", params={"provider": "anilist"})
    assert resp.status_code == 503


DESKTOP = "http://localhost:47300"


async def test_sign_in_from_the_desktop_app_hands_the_session_over(client, providers):
    # The desktop app's proxy says which origin the browser uses.
    start = await client.get(
        "/auth/login", params={"provider": "mal"}, headers={"x-notflix-origin": DESKTOP}
    )
    done = await client.get(
        "/auth/callback", params={"code": "c", "state": _state(start.headers["location"])}
    )
    location = done.headers["location"]
    assert location.startswith(f"{DESKTOP}/api/auth/handoff?token=")
    token = parse_qs(urlsplit(location).query)["token"][0]

    # The desktop origin has a session of its own: the handoff sets it, once.
    client.cookies.clear()
    assert (await client.get("/me")).status_code == 401
    back = await client.get("/auth/handoff", params={"token": token, "to": "/?login=ok"})
    assert back.headers["location"] == "/?login=ok"
    assert (await client.get("/me")).json()["name"] == "mal-user"
    client.cookies.clear()
    again = await client.get("/auth/handoff", params={"token": token})
    assert again.headers["location"] == "/login?login=failed&reason=expired"
    assert (await client.get("/me")).status_code == 401


async def test_desktop_sign_in_with_both_returns_to_the_desktop(client, providers):
    start = await client.get(
        "/auth/login",
        params={"provider": "mal", "then": "anilist"},
        headers={"x-notflix-origin": DESKTOP},
    )
    first = await client.get(
        "/auth/callback", params={"code": "c", "state": _state(start.headers["location"])}
    )
    # Signed in on the desktop, which then starts the AniList sign-in itself (its proxy has the
    # API key; the server's web app may not).
    location = urlsplit(first.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        f"{DESKTOP}/api/auth/handoff"
    )
    query = parse_qs(location.query)
    assert query["to"] == ["/api/auth/login?provider=anilist&link=true"]
    client.cookies.clear()
    await client.get("/auth/handoff", params={"token": query["token"][0]})
    start = await client.get(
        "/auth/login",
        params={"provider": "anilist", "link": "true"},
        headers={"x-notflix-origin": DESKTOP},
    )
    done = await client.get(
        "/auth/anilist/callback", params={"code": "c", "state": _state(start.headers["location"])}
    )
    location = done.headers["location"]
    assert location.startswith(f"{DESKTOP}/api/auth/handoff?token=")
    assert parse_qs(urlsplit(location).query)["to"] == ["/settings?login=ok&account=anilist"]
    client.cookies.clear()
    await client.get(
        "/auth/handoff", params={"token": parse_qs(urlsplit(location).query)["token"][0]}
    )
    me = (await client.get("/me")).json()
    assert (me["mal"], me["anilist"]) == ({"name": "mal-user"}, {"name": "al-user"})


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "http://localhost:3000", "javascript:alert(1)", ""]
)
async def test_other_origins_are_ignored(client, providers, origin):
    start = await client.get(
        "/auth/login", params={"provider": "mal"}, headers={"x-notflix-origin": origin}
    )
    done = await client.get(
        "/auth/callback", params={"code": "c", "state": _state(start.headers["location"])}
    )
    assert done.headers["location"] == "http://localhost:3000/?login=ok&account=mal"


@pytest.mark.parametrize("to", ["https://evil.example/", "//evil.example/", "/\\evil.example"])
async def test_handoff_stays_on_its_origin(client, providers, to):
    from app.core.cache import redis

    await redis().set("handoff:t", 1, ex=60)
    res = await client.get("/auth/handoff", params={"token": "t", "to": to})
    assert res.headers["location"] == "/"


async def test_failed_sign_ins_say_why(client, providers, monkeypatch):
    from app.api import auth

    async def bad_secret(code, verifier):
        raise auth.mal.MalError("MAL token request failed (401): invalid_client")

    # Not allowed at MAL.
    start = await client.get("/auth/login", params={"provider": "mal"})
    state = _state(start.headers["location"])
    denied = await client.get("/auth/callback", params={"error": "access_denied", "state": state})
    assert denied.headers["location"].endswith("/login?login=failed&provider=mal&reason=denied")
    # The client secret is wrong: MAL doesn't hand out a token.
    monkeypatch.setattr(auth.mal, "exchange_code", bad_secret)
    start = await client.get("/auth/login", params={"provider": "mal"})
    state = _state(start.headers["location"])
    bad = await client.get("/auth/callback", params={"code": "c", "state": state})
    assert bad.headers["location"].endswith("/login?login=failed&provider=mal&reason=token")
    # Unknown (or used) state.
    again = await client.get("/auth/callback", params={"code": "c", "state": state})
    assert again.headers["location"].endswith("&provider=mal&reason=expired")


async def test_the_first_sign_in_and_linking_sync_the_list(client, providers):
    await _sign_in(client, "mal")
    me = (await client.get("/me")).json()
    assert providers == [me["id"]]  # first sign-in: synced
    with sync_session() as db:
        db.get(User, me["id"]).last_synced_at = datetime.now(UTC)
        db.commit()
    await client.post("/auth/logout")
    await _sign_in(client, "mal")
    assert providers == [me["id"]]  # synced before: not again
    await _sign_in(client, "anilist", link="true")
    assert providers == [me["id"], me["id"]]  # another list linked: synced again
