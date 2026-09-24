import json

import httpx
import pytest

from app.providers import animetoast, anivexa, aniworld, reanime
from app.providers.anivexa import AnivexaProvider, available_options, parse_watch
from app.providers.aniworld import (
    AniWorldProvider,
    count_episodes,
    parse_episode_links,
    slug_candidates,
)
from app.providers.base import AnimeInfo, ProviderError, Stream
from app.services.anilist import parse_media

pytestmark = pytest.mark.anyio


@pytest.fixture
def memory_cache(monkeypatch):
    store: dict[str, object] = {}

    async def get_json(key):
        return store.get(key)

    async def set_json(key, value, ttl):
        store[key] = json.loads(json.dumps(value))

    for module in (anivexa, aniworld, animetoast, reanime):
        monkeypatch.setattr(module, "get_json", get_json)
        monkeypatch.setattr(module, "set_json", set_json)
    return store


def _node(id_, fmt, english, prequel=None):
    edges = [{"relationType": "PREQUEL", "node": prequel}] if prequel else []
    edges.append({"relationType": "SEQUEL", "node": {"id": 999, "type": "ANIME", "format": "TV"}})
    return {
        "id": id_,
        "type": "ANIME",
        "format": fmt,
        "title": {"english": english, "romaji": None},
        "synonyms": [],
        "relations": {"edges": edges},
    }


# --- AniList -----------------------------------------------------------------------------------


def test_anilist_season_counts_tv_prequels_only():
    s1 = _node(1, "TV", "Attack on Titan")
    ova = _node(2, "OVA", "Attack on Titan OVA", prequel=s1)
    s2 = _node(3, "TV", "Attack on Titan Season 2", prequel=ova)
    s3 = _node(4, "TV", "Attack on Titan Season 3", prequel=s2)

    info = parse_media(s3)
    assert info.id == 4
    assert info.season == 3
    assert info.titles == ["Attack on Titan Season 3"]
    assert info.root_titles == ["Attack on Titan"]


def test_anilist_movies_default_to_season_one():
    movie = _node(5, "MOVIE", "The Movie", prequel=_node(1, "TV", "Show"))
    assert parse_media(movie).season == 1


# --- Anivexa -----------------------------------------------------------------------------------

EPISODES = {
    "page": 1,
    "type": "filtered",
    "anizone": {"episodes": {"sub": [{"number": 1}, {"number": 2}], "dub": [{"number": 1}]}},
    "kaa": {"episodes": {"sub": [{"number": "2"}]}},
    "anikoto": {"error": "HTTP 403"},
}

WATCH = {
    "anilistId": 16498,
    "episode": 2,
    "intro": {"start": 85, "end": 175},
    "outro": None,
    "streams": [
        {"url": "https://embed.example/e/2", "type": "embed", "server": "Embed"},
        {"url": "https://cdn.example/dash.mpd", "type": "dash", "server": "Dash"},
        {
            "url": "https://cdn.example/master.m3u8",
            "type": "hls",
            "server": "HD-1",
            "referer": "https://site.example/",
            "subtitles": [
                {"url": "https://cdn.example/en.vtt", "label": "English", "srclang": "en"}
            ],
        },
    ],
}


def test_available_options_filters_by_episode_and_skips_errors():
    assert available_options(EPISODES, 1) == [("anizone", "sub"), ("anizone", "dub")]
    assert available_options(EPISODES, 2) == [("anizone", "sub"), ("kaa", "sub")]


def test_parse_watch_maps_streams_subtitles_and_intro():
    resolved = parse_watch(WATCH, "anizone")
    hls, embed = resolved.streams
    assert (hls.kind, hls.format, hls.label) == ("direct", "hls", "HD-1")
    assert hls.headers == {"Referer": "https://site.example/"}
    assert hls.subtitles[0].label == "English"
    assert hls.subtitles[0].headers == {"Referer": "https://site.example/"}
    assert (embed.kind, embed.url) == ("embed", "https://embed.example/e/2")
    assert [(s.kind, s.start_s, s.end_s) for s in resolved.segments] == [("opening", 85, 175)]


async def test_anivexa_provider_options_and_resolve(monkeypatch, memory_cache):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path.startswith("/episodes/"):
            return httpx.Response(200, json=EPISODES)
        if request.url.path == "/watch/kaa/16498/sub/kaa-2":
            return httpx.Response(200, json=WATCH)
        return httpx.Response(404, json={"error": "Not found"})

    async def fake_anilist_id(mal_id):
        return 16498

    monkeypatch.setattr(anivexa, "anilist_id", fake_anilist_id)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AnivexaProvider("http://anivexa:4000/", ["anizone", "kaa", "anikoto"], http=http)
    anime = AnimeInfo(id=16498, title="Shingeki no Kyojin")

    options = await provider.options(anime, 2)
    assert [(o.id, o.label, o.language) for o in options] == [
        ("anivexa:anizone:sub", "AniZone", "en-sub"),
        ("anivexa:kaa:sub", "KickAssAnime", "en-sub"),
    ]
    assert requests[0] == "http://anivexa:4000/episodes/anizone/kaa/anikoto/16498?map=false"

    await provider.options(anime, 1)
    assert len(requests) == 1  # episode list came from the cache

    resolved = await provider.resolve(anime, 2, "kaa:sub")
    assert resolved.streams[0].url == "https://cdn.example/master.m3u8"

    with pytest.raises(ProviderError, match="404"):
        await provider.resolve(anime, 2, "anizone:dub")
    with pytest.raises(ProviderError, match="Unknown"):
        await provider.resolve(anime, 2, "mkissa:sub")


async def test_anivexa_does_not_cache_total_failures(monkeypatch, memory_cache):
    failed = {"page": 1, "anizone": {"error": "No data found for AniList ID 1"}}
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=failed))
    )

    async def fake_anilist_id(mal_id):
        return 1

    monkeypatch.setattr(anivexa, "anilist_id", fake_anilist_id)
    provider = AnivexaProvider("http://anivexa:4000", ["anizone"], http=http)
    with pytest.raises(ProviderError, match="Every Anivexa provider failed"):
        await provider.options(AnimeInfo(id=1, title="x"), 1)
    assert memory_cache == {}


# --- AniWorld ----------------------------------------------------------------------------------

NEW_STYLE_EPISODE = """
<div id="episode-links">
  <button class="link-box" data-play-url="/r?t=abc" data-provider-name="VOE">
    <svg><use href="#icon-flag-german"></use></svg>
  </button>
  <button class="link-box" data-play-url="https://aniworld.to/r?t=def"
          data-provider-name="Doodstream">
    <svg><use href="#icon-flag-japanese-german"></use></svg>
  </button>
  <button class="link-box" data-play-url="/r?t=ghi" data-provider-name="VOE">
    <svg><use xlink:href="#icon-flag-japanese-english"></use></svg>
  </button>
</div>
"""

OLD_STYLE_EPISODE = """
<ul>
  <li class="episodeLink1" data-lang-key="3" data-link-target="/redirect/123">
    <a class="watchEpisode"><i class="icon VOE"></i><h4>VOE</h4></a>
  </li>
</ul>
"""

SEASON_PAGE = """
<section class="episode-section"><table><tbody>
  <tr class="episode-row"><th class="episode-number-cell">1</th></tr>
  <tr class="episode-row"><th class="episode-number-cell">2</th></tr>
</tbody></table></section>
"""


def test_parse_new_style_episode_links():
    links = parse_episode_links(NEW_STYLE_EPISODE)
    assert [(link.path, link.hoster, link.language) for link in links] == [
        ("/r?t=abc", "VOE", "de-dub"),
        ("/r?t=def", "Doodstream", "de-sub"),
        ("/r?t=ghi", "VOE", "en-sub"),
    ]


def test_parse_old_style_episode_links():
    [link] = parse_episode_links(OLD_STYLE_EPISODE)
    assert (link.path, link.hoster, link.language) == ("/redirect/123", "VOE", "de-sub")


def test_count_episodes():
    assert count_episodes(SEASON_PAGE) == 2
    assert count_episodes('<div class="messageAlert danger">Nicht gefunden</div>') == 0


def test_slug_candidates():
    assert slug_candidates(
        ["Re:ZERO -Starting Life in Another World- Season 2", "Steins;Gate"]
    ) == [
        "rezero-starting-life-in-another-world-season-2",
        "rezero-starting-life-in-another-world",
        "steinsgate",
    ]
    assert slug_candidates(["Kimetsu no Yaiba: Yuukaku-hen", "Pokémon"]) == [
        "kimetsu-no-yaiba-yuukaku-hen",
        "pokemon",
    ]


def _aniworld_handler(requests):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.raw_path.decode())
        path = request.url.path
        if path in ("/anime/attack-on-titan/staffel-3", "/anime/attack-on-titan/staffel-1"):
            return httpx.Response(200, text=SEASON_PAGE)
        if path == "/anime/attack-on-titan/staffel-3/episode-2":
            return httpx.Response(200, text=NEW_STYLE_EPISODE)
        if path == "/r":
            return httpx.Response(302, headers={"location": "https://voe.example/e/xyz"})
        if path == "/redirect/9":
            return httpx.Response(200, text="captcha")
        return httpx.Response(404)

    return handler


async def test_aniworld_locates_series_and_lists_german_sources(
    database, monkeypatch, memory_cache
):
    from app.services import anilist
    from app.services.anilist import AniListInfo
    from app.services.mappings import delete_mapping, get_mapping

    async def fake_lookup(mal_id):
        return AniListInfo(
            id=104578,
            season=3,
            titles=["Attack on Titan Season 3"],
            root_titles=["Shingeki no Kyojin", "Attack on Titan"],
        )

    monkeypatch.setattr(anilist, "lookup", fake_lookup)
    await delete_mapping(35760, "aniworld")
    requests: list[str] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(_aniworld_handler(requests)))
    provider = AniWorldProvider("https://aniworld.example", "anime/{slug}", http=http)
    anime = AnimeInfo(id=35760, title="Shingeki no Kyojin Season 3")

    options = await provider.options(anime, 2)
    assert [(o.label, o.language) for o in options] == [
        ("VOE", "de-dub"),
        ("Doodstream", "de-sub"),
        ("VOE", "en-sub"),
    ]
    assert requests[:2] == [
        "/anime/shingeki-no-kyojin/staffel-3",
        "/anime/attack-on-titan/staffel-3",
    ]
    mapping = await get_mapping(35760, "aniworld")
    assert (mapping.external_id, mapping.season, mapping.manual) == ("attack-on-titan", 3, False)

    resolved = await provider.resolve(anime, 2, options[0].key)
    assert [(s.kind, s.url, s.label) for s in resolved.streams] == [
        ("embed", "https://voe.example/e/xyz", "voe.example")
    ]
    # No redirect (e.g. a captcha page): the iframe loads AniWorld's link itself.
    fallback = await provider.resolve(anime, 2, "/redirect/9")
    assert fallback.streams[0].url == "https://aniworld.example/redirect/9"

    with pytest.raises(ProviderError):
        await provider.resolve(anime, 2, "//evil.example/x")


async def test_aniworld_remembers_missing_series(database, monkeypatch, memory_cache):
    from app.services import anilist
    from app.services.mappings import delete_mapping

    async def not_on_anilist(mal_id):
        return None

    monkeypatch.setattr(anilist, "lookup", not_on_anilist)
    await delete_mapping(1, "aniworld")
    requests: list[str] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(_aniworld_handler(requests)))
    provider = AniWorldProvider("https://aniworld.example", "anime/{slug}", http=http)
    anime = AnimeInfo(id=1, title="Unknown Show")

    assert await provider.options(anime, 1) == []
    assert requests == ["/anime/unknown-show/staffel-1"]
    assert await provider.options(anime, 1) == []
    assert len(requests) == 1


async def test_aniworld_does_not_remember_guesses_made_while_anilist_is_down(
    database, monkeypatch, memory_cache
):
    from app.services import anilist
    from app.services.mappings import delete_mapping, get_mapping

    async def anilist_down(mal_id):
        raise anilist.AniListUnavailable("down")

    monkeypatch.setattr(anilist, "lookup", anilist_down)
    await delete_mapping(2, "aniworld")
    requests: list[str] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(_aniworld_handler(requests)))
    provider = AniWorldProvider("https://aniworld.example", "anime/{slug}", http=http)

    assert await provider.options(AnimeInfo(id=2, title="Unknown Show"), 1) == []
    assert await provider.options(AnimeInfo(id=2, title="Unknown Show"), 1) == []
    assert len(requests) == 2
    assert await get_mapping(2, "aniworld") is None

    # A successful guess isn't persisted either, but is reused for a while.
    titan = AnimeInfo(id=3, title="Attack on Titan")
    await delete_mapping(3, "aniworld")
    requests.clear()
    await provider.options(titan, 1)
    await provider.options(titan, 2)
    assert requests.count("/anime/attack-on-titan/staffel-1") == 1
    assert await get_mapping(3, "aniworld") is None


async def test_anilist_backs_off_after_failures(monkeypatch):
    from app.services import anilist

    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr(anilist, "_down_until", 0.0)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(anilist.AniListUnavailable):
        await anilist.lookup(1, http=http)
    with pytest.raises(anilist.AniListUnavailable):
        await anilist.lookup(1, http=http)
    assert len(calls) == 1


# --- ReAnime -----------------------------------------------------------------------------------

SEARCH = {
    "data": [
        {
            "slug": "shingeki-no-kyojin-s3-aaa",
            "title": {"english": "Attack on Titan Season 3"},
            "cover_image": {"large": "https://s4.anilist.co/file/bx99147-abc.jpg"},
        },
        {
            "slug": "shingeki-no-kyojin-bbb",
            "title": {"english": "Attack on Titan"},
            "anilist": 16498,
        },
    ]
}
SERVERS = {
    "sub": [
        {"serverName": "HD-2", "dataLink": "https://flixcloud.cc/e/abc?v=2", "dataType": "sub"},
        {"serverName": "HD-1", "dataLink": "javascript:alert(1)", "dataType": "sub"},
    ],
    "dub": [
        {"serverName": "HD-1", "dataLink": "https://flixcloud.cc/e/abc?v=1", "dataType": "dub"}
    ],
    "intro_start": 90,
    "intro_end": 180,
    "outro_start": None,
    "outro_end": None,
}


def test_reanime_pick_slug_prefers_anilist_id():
    from app.providers.reanime import pick_slug

    results = SEARCH["data"]
    assert pick_slug(results, 99147, ["Attack on Titan"]) == "shingeki-no-kyojin-s3-aaa"
    assert pick_slug(results, 16498, []) == "shingeki-no-kyojin-bbb"
    assert pick_slug(results, 1, ["Attack on Titan"]) is None  # ids known: never guess by title
    untagged = [{"slug": "x", "title": "Steins;Gate"}]
    assert pick_slug(untagged, 9253, ["Steins Gate"]) == "x"


async def test_reanime_provider_lists_embed_servers(database, monkeypatch, memory_cache):
    from app.providers.reanime import ReAnimeProvider
    from app.services import anilist
    from app.services.mappings import delete_mapping

    async def fake_anilist_id(mal_id):
        return 99147

    monkeypatch.setattr(anilist, "anilist_id", fake_anilist_id)
    await delete_mapping(38524, "reanime")
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/search":
            return httpx.Response(200, json=SEARCH)
        if request.url.path == "/servers/shingeki-no-kyojin-s3-aaa/3":
            return httpx.Response(200, json=SERVERS)
        return httpx.Response(404, json={"detail": "Not found"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = ReAnimeProvider("http://reanime:8000/", http=http)
    anime = AnimeInfo(id=38524, title="Shingeki no Kyojin Season 3", title_en="Attack on Titan S3")

    options = await provider.options(anime, 3)
    assert [(o.id, o.label, o.language) for o in options] == [
        ("reanime:sub:HD-2", "ReAnime HD-2", "en-sub"),
        ("reanime:dub:HD-1", "ReAnime HD-1", "en-dub"),
    ]
    stream = options[0].resolved.streams[0]
    assert (stream.kind, stream.url) == ("embed", "https://flixcloud.cc/e/abc?v=2")
    assert [(s.kind, s.start_s, s.end_s) for s in options[0].resolved.segments] == [
        ("opening", 90, 180)
    ]
    assert requests[1] == "http://reanime:8000/servers/shingeki-no-kyojin-s3-aaa/3?anilist_id=99147"
    assert (await provider.resolve(anime, 3, "dub:HD-1")).streams[0].url.endswith("v=1")
    assert await provider.options(anime, 99) == []


async def _async(value):
    return value


# --- Unreachable providers ---------------------------------------------------------------------


class DownProvider:
    name = "down"
    base_url = "http://localhost:4000"

    def __init__(self):
        self.calls = 0

    async def options(self, anime, episode):
        self.calls += 1
        raise httpx.ConnectError("All connection attempts failed")

    async def resolve(self, anime, episode, key):
        raise AssertionError("must not be called while the provider is down")


async def test_unreachable_provider_is_skipped_for_a_while(monkeypatch):
    from app.providers import base

    down = DownProvider()
    monkeypatch.setattr(base, "enabled_providers", lambda: [down])
    monkeypatch.setattr(base, "_down_until", {})
    anime = AnimeInfo(id=1, title="x")

    assert await base.list_options(anime, 1) == []
    assert await base.list_options(anime, 1) == []
    assert down.calls == 1
    with pytest.raises(base.ProviderUnavailable):
        await base.resolve_option(anime, 1, "down:key")


def test_unreachable_hint_mentions_host_docker_internal(monkeypatch):
    from pathlib import Path

    from app.providers.base import unreachable_hint

    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/.dockerenv")
    assert "http://host.docker.internal:4000" in unreachable_hint("http://localhost:4000")
    assert unreachable_hint("http://anivexa.lan:4000") == ""


async def test_anivexa_scan_uses_one_request(monkeypatch, memory_cache):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=EPISODES)

    async def fake_anilist_id(mal_id):
        return 16498

    monkeypatch.setattr(anivexa, "anilist_id", fake_anilist_id)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AnivexaProvider("http://anivexa:4000", ["anizone", "kaa"], http=http)
    found = await provider.scan(AnimeInfo(id=16498, title="x"), [1, 2, 3])
    assert [len(found[ep]) for ep in (1, 2, 3)] == [2, 2, 0]
    assert len(requests) == 1


async def test_aniworld_scan_only_fetches_listed_episodes(database, monkeypatch, memory_cache):
    from app.services import anilist
    from app.services.mappings import save_mapping

    await save_mapping(35760, "aniworld", "attack-on-titan", 3)
    requests: list[str] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(_aniworld_handler(requests)))
    provider = AniWorldProvider("https://aniworld.example", "anime/{slug}", http=http)
    monkeypatch.setattr(anilist, "lookup", lambda mal_id: pytest.fail("mapping is cached"))

    found = await provider.scan(AnimeInfo(id=35760, title="x"), [1, 2, 3, 4])
    assert [len(found[ep]) for ep in (1, 2, 3, 4)] == [0, 3, 0, 0]
    # SEASON_PAGE lists episodes 1 and 2; episodes 3 and 4 are never requested.
    assert sorted(requests) == [
        "/anime/attack-on-titan/staffel-3",
        "/anime/attack-on-titan/staffel-3/episode-1",
        "/anime/attack-on-titan/staffel-3/episode-2",
    ]


def test_season_episode_numbers():
    from app.providers.aniworld import season_episode_numbers

    assert season_episode_numbers(SEASON_PAGE) == {1, 2}
    old = '<table class="seasonEpisodesList"><meta itemprop="episodeNumber" content="7"></table>'
    assert season_episode_numbers(old) == {7}


# --- AniWorld through a self-hosted API ---------------------------------------------------------

API_SEASON = [
    {
        "number": n,
        "title": "",
        "originalTitle": f"Episode {n}",
        "hosters": ["VOE", "Doodstream"],
        "languages": [{"audio": "English", "subtitle": "German"}],
    }
    for n in range(1, 12)
]
API_SEASON[0]["languages"].append({"audio": "German", "subtitle": None})
API_EPISODE = {
    "number": 5,
    "season": 1,
    "title": "",
    "originalTitle": "Episode 5",
    "description": "",
    "streams": [
        {
            "videoUrl": "http://186.2.175.5/r?t=voe",
            "hoster": "VOE",
            "language": {"audio": "English", "subtitle": "German"},
        },
        {
            "videoUrl": "http://186.2.175.5/r?t=dood",
            "hoster": "Doodstream",
            "language": {"audio": "English", "subtitle": "German"},
        },
        {
            "videoUrl": "http://186.2.175.5/r?t=dub",
            "hoster": "VOE",
            "language": {"audio": "German", "subtitle": None},
        },
    ],
}


def test_api_language():
    from app.providers.aniworld import api_language

    assert api_language({"audio": "English", "subtitle": "German"}) == "de-sub"
    assert api_language({"audio": "Japanese", "subtitle": "German"}) == "de-sub"
    assert api_language({"audio": "German", "subtitle": None}) == "de-dub"
    assert api_language({"audio": "German", "subtitle": "German"}) == "de-dub"
    assert api_language({"audio": "Japanese", "subtitle": "English"}) == "en-sub"
    assert api_language({"audio": "English"}) == "en-dub"
    assert api_language(None) == "unknown"


def _api_handler(requests):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.raw_path.decode())
        path = request.url.path
        if path == "/api/series/dress-up-darling/episodes/1":
            return httpx.Response(200, json=API_SEASON)
        if path == "/api/series/dress-up-darling/episodes/1/5":
            return httpx.Response(200, json=API_EPISODE)
        if path == "/api/series/broken/episodes/1":
            return httpx.Response(500, text="SerienStream is down")
        if request.url.host == "186.2.175.5":
            return httpx.Response(
                302, headers={"location": f"https://voe.example/e/{request.url.query.decode()}"}
            )
        return httpx.Response(404, json={"error": "Series not found"})

    return handler


async def test_aniworld_api_provider(database, monkeypatch, memory_cache):
    from app.providers.aniworld import AniWorldApiProvider
    from app.services import anilist
    from app.services.anilist import AniListInfo
    from app.services.mappings import delete_mapping, get_mapping

    async def fake_lookup(mal_id):
        return AniListInfo(
            id=1, season=1, titles=["My Dress-Up Darling"], root_titles=["Dress-Up Darling"]
        )

    monkeypatch.setattr(anilist, "lookup", fake_lookup)
    await delete_mapping(48736, "aniworld")
    requests: list[str] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(_api_handler(requests)))
    provider = AniWorldApiProvider("http://aniworld-api:5000/", http=http)
    anime = AnimeInfo(id=48736, title="Sono Bisque Doll wa Koi wo Suru")

    found = await provider.scan(anime, list(range(1, 14)))
    assert [(o.id, o.label, o.language) for o in found[1]] == [
        ("aniworld:de-sub", "VOE / Doodstream", "de-sub"),
        ("aniworld:de-dub", "VOE / Doodstream", "de-dub"),
    ]
    assert [o.language for o in found[5]] == ["de-sub"]
    assert found[12] == [] and found[13] == []
    assert requests == [
        "/api/series/dress-up-darling/episodes/1",  # the first-season title is tried first
    ]
    assert (await get_mapping(48736, "aniworld")).external_id == "dress-up-darling"

    requests.clear()
    await provider.scan(anime, [1, 2])
    assert requests == []  # season list cached

    resolved = await provider.resolve(anime, 5, "de-sub")
    assert [(s.kind, s.url, s.label) for s in resolved.streams] == [
        ("embed", "https://voe.example/e/t=voe", "VOE"),
        ("embed", "https://voe.example/e/t=dood", "Doodstream"),
    ]
    assert (await provider.resolve(anime, 5, "de-dub")).streams[0].url.endswith("t=dub")
    with pytest.raises(ProviderError, match="No en-sub stream"):
        await provider.resolve(anime, 5, "en-sub")


async def test_aniworld_api_errors_are_not_remembered_as_missing(
    database, monkeypatch, memory_cache
):
    from app.providers.aniworld import AniWorldApiProvider
    from app.services import anilist
    from app.services.mappings import delete_mapping, get_mapping

    async def not_on_anilist(mal_id):
        return None

    monkeypatch.setattr(anilist, "lookup", not_on_anilist)
    await delete_mapping(4, "aniworld")
    http = httpx.AsyncClient(transport=httpx.MockTransport(_api_handler([])))
    provider = AniWorldApiProvider("http://aniworld-api:5000", http=http)

    with pytest.raises(ProviderError, match="lookup failed"):
        await provider.scan(AnimeInfo(id=4, title="Broken"), [1])
    assert await get_mapping(4, "aniworld") is None

    # A plain 404 is a real "not found" and is remembered.
    assert await provider.scan(AnimeInfo(id=4, title="Unknown Show"), [1]) == {1: []}
    assert (await get_mapping(4, "aniworld")).external_id is None


# --- AniScraper (bundled service) --------------------------------------------------------------

SCRAPER_SEARCH = [
    {
        "slug": "attack-on-titan-junior-high",
        "title": "Attack on Titan: Junior High",
        "description": "",
        "url": "https://aniworld.to/anime/stream/attack-on-titan-junior-high",
    },
    {
        "slug": "attack-on-titan",
        "title": "Attack on Titan",
        "description": "",
        "url": "https://aniworld.to/anime/stream/attack-on-titan",
    },
]
SCRAPER_SERIES = {
    "slug": "attack-on-titan",
    "title": "Attack on Titan",
    "description": None,
    "url": "https://aniworld.to/anime/stream/attack-on-titan",
    "seasons": [
        {
            "season": 3,
            "name": "Season 3",
            "episodes": [
                {
                    "episode": n,
                    "title_de": None,
                    "title_en": f"Ep {n}",
                    "url": f"https://aniworld.to/anime/stream/attack-on-titan/staffel-3/episode-{n}",
                    "hosters": ["VOE", "Filemoon"],
                    "languages": ["German Dub", "German Sub"] if n == 1 else ["German Sub"],
                }
                for n in (1, 2)
            ],
        }
    ],
}
SCRAPER_EPISODE = {
    "slug": "attack-on-titan",
    "season": 3,
    "episode": 2,
    "languages": ["English Sub", "German Sub"],
    "streams": {
        "German Sub": [
            {
                "hoster": "VOE",
                "url": "https://aniworld.to/redirect/456",
                "link_id": "456",
                "direct_url": None,
            },
            {
                "hoster": "Filemoon",
                "url": "https://aniworld.to/redirect/457",
                "link_id": "457",
                "direct_url": "https://cdn.example/hls/457/master.m3u8?t=1",
            },
        ],
        "English Sub": [
            {"hoster": "VOE", "url": "https://aniworld.to/redirect/789", "link_id": "789"}
        ],
    },
}


def _scraper_handler(requests):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url).removeprefix("http://aniscraper:8000"))
        path = request.url.path
        if path == "/search/titles":
            assert request.url.params["source"] == "aniworld"
            q = request.url.params["q"]
            if "Kyojin" in q:  # aniworld.to failing while animetoast answers
                return httpx.Response(200, json={"aniworld": {"error": "aniworld.to returned 503"}})
            return httpx.Response(200, json={"aniworld": SCRAPER_SEARCH if "Titan" in q else []})
        if path == "/anime/attack-on-titan" and request.url.params.get("season") == "3":
            return httpx.Response(200, json=SCRAPER_SERIES)
        if path.startswith("/anime/") and path.count("/") == 2:
            return httpx.Response(200, json={**SCRAPER_SERIES, "seasons": []})
        if path == "/anime/attack-on-titan/season/3/episode/2":
            assert request.url.params["direct"] == "true"
            return httpx.Response(200, json=SCRAPER_EPISODE)
        if request.url.host == "aniworld.to":
            return httpx.Response(302, headers={"location": f"https://voe.example{path}"})
        return httpx.Response(404, json={"detail": "Not found"})

    return handler


async def test_aniscraper_provider(database, monkeypatch, memory_cache):
    from app.providers.aniworld import AniScraperProvider
    from app.services import anilist
    from app.services.anilist import AniListInfo
    from app.services.mappings import delete_mapping, get_mapping

    async def fake_lookup(mal_id):
        return AniListInfo(
            id=104578,
            season=3,
            titles=["Attack on Titan Season 3"],
            root_titles=["Attack on Titan"],
        )

    monkeypatch.setattr(anilist, "lookup", fake_lookup)
    await delete_mapping(35760, "aniworld")
    requests: list[str] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(_scraper_handler(requests)))
    provider = AniScraperProvider("http://aniscraper:8000", http=http)
    anime = AnimeInfo(id=35760, title="Shingeki no Kyojin Season 3")

    found = await provider.scan(anime, [1, 2, 3])
    assert [(o.id, o.label, o.language) for o in found[1]] == [
        ("aniworld:de-dub", "VOE / Filemoon", "de-dub"),
        ("aniworld:de-sub", "VOE / Filemoon", "de-sub"),
    ]
    assert [o.language for o in found[2]] == ["de-sub"] and found[3] == []
    # The search hit whose title matches exactly is tried before the other hit.
    assert requests[0] == "/search/titles?q=Attack+on+Titan&source=aniworld"
    assert [r for r in requests if r.startswith("/anime/")] == [
        "/anime/attack-on-titan?season=3&streams=false"
    ]
    assert (await get_mapping(35760, "aniworld")).external_id == "attack-on-titan"

    requests.clear()
    resolved = await provider.resolve(anime, 2, "de-sub")
    # Filemoon's direct file replaces its embed and comes first; VOE has none and stays embedded.
    assert [(s.kind, s.format, s.url, s.label) for s in resolved.streams] == [
        ("direct", "hls", "https://cdn.example/hls/457/master.m3u8?t=1", "Filemoon"),
        ("embed", None, "https://voe.example/redirect/456", "VOE"),
    ]
    assert "https://aniworld.to/redirect/457" not in requests  # no redirect to follow
    assert len((await provider.resolve(anime, 2, "en-sub")).streams) == 1
    with pytest.raises(ProviderError, match="No de-dub stream"):
        await provider.resolve(anime, 2, "de-dub")


async def test_aniscraper_outage_is_not_remembered(database, monkeypatch, memory_cache):
    from app.providers.aniworld import AniScraperProvider
    from app.services import anilist
    from app.services.mappings import delete_mapping, get_mapping

    async def not_on_anilist(mal_id):
        return None

    monkeypatch.setattr(anilist, "lookup", not_on_anilist)
    await delete_mapping(5, "aniworld")
    down = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(502, json={"detail": "Could not reach aniworld.to"})
        )
    )
    provider = AniScraperProvider("http://aniscraper:8000", http=down)
    with pytest.raises(ProviderError, match="lookup failed"):
        await provider.scan(AnimeInfo(id=5, title="Naruto"), [1])
    assert await get_mapping(5, "aniworld") is None


# --- AnimeToast (via AniScraper) ---------------------------------------------------------------

TOAST_SEARCH = {
    "animetoast": [
        {
            "slug": "shingeki-no-kyojin-season-3-ger-sub",
            "title": "Shingeki no Kyojin Season 3 Ger Sub",
            "language": "German Sub",
            "url": "https://www.animetoast.cc/shingeki-no-kyojin-season-3-ger-sub/",
        },
        {
            "slug": "shingeki-no-kyojin-season-3-ger-dub",
            "title": "Shingeki no Kyojin Season 3 Ger Dub",
            "language": "German Dub",
            "url": "https://www.animetoast.cc/shingeki-no-kyojin-season-3-ger-dub/",
        },
        {
            "slug": "shingeki-no-kyojin-ger-sub",
            "title": "Shingeki no Kyojin Ger Sub",
            "language": "German Sub",
            "url": "https://www.animetoast.cc/shingeki-no-kyojin-ger-sub/",
        },
    ]
}


def _toast_show(slug, language, numbers):
    return {
        "source": "animetoast",
        "slug": slug,
        "title": slug,
        "language": language,
        "url": f"https://www.animetoast.cc/{slug}/",
        "seasons": [
            {
                "season": 1,
                "name": "Season 1",
                "episodes": [
                    {
                        "episode": n,
                        "hosters": ["Voe", "Doodstream"],
                        "languages": [language],
                        "streams": {
                            language: [
                                {
                                    "hoster": "Voe",
                                    "url": f"https://www.animetoast.cc/{slug}/?link={n}",
                                }
                            ]
                        },
                    }
                    for n in numbers
                ],
            }
        ],
    }


def _toast_handler(requests):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url).removeprefix("http://aniscraper:8000"))
        path = request.url.path
        if path == "/search/titles":
            assert request.url.params["source"] == "animetoast"
            q = request.url.params["q"]
            return httpx.Response(200, json=TOAST_SEARCH if "Kyojin" in q else {"animetoast": []})
        if path == "/animetoast/shingeki-no-kyojin-season-3-ger-sub":
            return httpx.Response(200, json=_toast_show("x-sub", "German Sub", [1, 2]))
        if path == "/animetoast/shingeki-no-kyojin-season-3-ger-dub":
            return httpx.Response(200, json=_toast_show("x-dub", "German Dub", [1]))
        if path == "/animetoast/shingeki-no-kyojin-season-3-ger-sub/episode/2":
            assert request.url.params["direct"] == "true"
            return httpx.Response(
                200,
                json={
                    "source": "animetoast",
                    "slug": "x",
                    "language": "German Sub",
                    "episode": 2,
                    "hosters": ["Voe", "Doodstream"],
                    "languages": ["German Sub"],
                    "streams": {
                        "German Sub": [
                            {
                                "hoster": "Voe",
                                "url": "https://voe.example/e/2",
                                "page_url": "https://www.animetoast.cc/x/?link=2",
                                "direct_url": None,
                            },
                            {
                                "hoster": "Doodstream",
                                "url": "//dood.example/e/2",
                                "page_url": "https://www.animetoast.cc/x/?link=5",
                                "direct_url": "https://cdn.example/v/2.mp4",
                            },
                            {
                                "hoster": "Broken",
                                "url": "https://www.animetoast.cc/x/?link=9",
                                "error": "timeout",
                            },
                        ]
                    },
                },
            )
        return httpx.Response(404, json={"detail": "Not found"})

    return handler


def test_animetoast_pick_pages():
    from app.providers.animetoast import pick_pages

    titles = ["Attack on Titan Season 3", "Shingeki no Kyojin Season 3"]
    assert pick_pages(TOAST_SEARCH["animetoast"], titles) == [
        "shingeki-no-kyojin-season-3-ger-dub",
        "shingeki-no-kyojin-season-3-ger-sub",
    ]
    assert pick_pages(TOAST_SEARCH["animetoast"], ["Naruto"]) == []  # never a loose guess


async def test_animetoast_provider(database, monkeypatch, memory_cache):
    from app.providers.animetoast import AnimeToastProvider
    from app.services import anilist
    from app.services.anilist import AniListInfo
    from app.services.mappings import delete_mapping, get_mapping

    async def fake_lookup(mal_id):
        return AniListInfo(
            id=104578,
            season=3,
            titles=["Attack on Titan Season 3", "Shingeki no Kyojin Season 3"],
            root_titles=["Attack on Titan"],
        )

    monkeypatch.setattr(anilist, "lookup", fake_lookup)
    await delete_mapping(35760, "animetoast")
    requests: list[str] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(_toast_handler(requests)))
    provider = AnimeToastProvider("http://aniscraper:8000", http=http)
    anime = AnimeInfo(id=35760, title="Shingeki no Kyojin Season 3")

    found = await provider.scan(anime, [1, 2, 3])
    assert [(o.id, o.label, o.language) for o in found[1]] == [
        ("animetoast:shingeki-no-kyojin-season-3-ger-dub", "Voe / Doodstream", "de-dub"),
        ("animetoast:shingeki-no-kyojin-season-3-ger-sub", "Voe / Doodstream", "de-sub"),
    ]
    assert [o.language for o in found[2]] == ["de-sub"] and found[3] == []
    mapping = await get_mapping(35760, "animetoast")
    assert mapping.external_id == (
        "shingeki-no-kyojin-season-3-ger-dub,shingeki-no-kyojin-season-3-ger-sub"
    )

    resolved = await provider.resolve(anime, 2, "shingeki-no-kyojin-season-3-ger-sub")
    assert [(s.kind, s.format, s.url, s.label) for s in resolved.streams] == [
        ("direct", "file", "https://cdn.example/v/2.mp4", "Doodstream"),
        ("embed", None, "https://voe.example/e/2", "Voe"),
    ]
    assert requests[-1] == "/animetoast/shingeki-no-kyojin-season-3-ger-sub/episode/2?direct=true"
    with pytest.raises(ProviderError, match="Unknown AnimeToast page"):
        await provider.resolve(anime, 2, "some-other-show-ger-dub")


async def test_animetoast_outage_is_not_remembered(database, monkeypatch, memory_cache):
    from app.providers.animetoast import AnimeToastProvider
    from app.services import anilist
    from app.services.mappings import delete_mapping, get_mapping

    async def not_on_anilist(mal_id):
        return None

    monkeypatch.setattr(anilist, "lookup", not_on_anilist)
    await delete_mapping(6, "animetoast")
    down = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"animetoast": {"error": "Could not reach animetoast.cc"}}
            )
        )
    )
    provider = AnimeToastProvider("http://aniscraper:8000", http=down)
    with pytest.raises(ProviderError, match="search failed"):
        await provider.scan(AnimeInfo(id=6, title="Naruto"), [1])
    assert await get_mapping(6, "animetoast") is None


async def test_animetoast_mapping_override(client, user):
    from app.services import source_scan
    from app.services.mappings import delete_mapping

    await delete_mapping(9, "animetoast")
    await source_scan.store_episode(9, "animetoast", 1, [])
    body = {"slugs": ["naruto-ger-dub", "naruto-ger-sub", "naruto-ger-dub"], "episode_offset": 2}
    assert (await client.put("/anime/9/mappings/animetoast", json=body)).status_code == 204
    assert await source_scan.cached_options(9, 1, "animetoast") is None  # cache dropped
    [mapping] = (await client.get("/anime/9/mappings")).json()
    assert (mapping["external_id"], mapping["episode_offset"], mapping["manual"]) == (
        "naruto-ger-dub,naruto-ger-sub",
        2,
        True,
    )
    bad = await client.put("/anime/9/mappings/animetoast", json={"slugs": ["../etc"]})
    assert bad.status_code == 422
    assert (await client.delete("/anime/9/mappings/animetoast")).status_code == 204


def test_hoster_direct():
    from app.api.streams import stream_out
    from app.providers.base import Resolved, hoster_direct, resolved_from_json, resolved_to_json

    assert hoster_direct({"direct_url": None}, "VOE") is None
    assert hoster_direct({}, "VOE") is None
    assert hoster_direct({"direct_url": "javascript:alert(1)"}, "VOE") is None
    hls = hoster_direct({"direct_url": "//cdn.example/x/Master.M3U8"}, "VOE")
    assert hls == Stream(
        kind="direct",
        url="https://cdn.example/x/Master.M3U8",
        label="VOE",
        format="hls",
        relay=True,
    )
    mp4 = hoster_direct({"direct_url": "https://cdn.example/v.mp4?m3u8=1"}, "D")
    assert mp4.format == "file"
    # Played through the proxy: the link belongs to the IP AniScraper extracted it from.
    assert stream_out(mp4).url.startswith("/api/proxy?t=")
    assert resolved_from_json(resolved_to_json(Resolved([mp4]))).streams == [mp4]
