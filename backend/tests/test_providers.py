import json

import httpx
import pytest

from app.providers import anivexa, aniworld
from app.providers.anivexa import AnivexaProvider, available_options, parse_watch
from app.providers.aniworld import (
    AniWorldProvider,
    count_episodes,
    parse_episode_links,
    slug_candidates,
)
from app.providers.base import AnimeInfo, ProviderError
from app.services.anilist import parse_media

pytestmark = pytest.mark.anyio


@pytest.fixture
def memory_cache(monkeypatch):
    store: dict[str, object] = {}

    async def get_json(key):
        return store.get(key)

    async def set_json(key, value, ttl):
        store[key] = json.loads(json.dumps(value))

    for module in (anivexa, aniworld):
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
    assert await provider.options(AnimeInfo(id=1, title="x"), 1) == []
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
        if path == "/anime/attack-on-titan/staffel-3":
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
    from app.providers import reanime
    from app.providers.reanime import ReAnimeProvider
    from app.services import anilist
    from app.services.mappings import delete_mapping

    async def fake_anilist_id(mal_id):
        return 99147

    monkeypatch.setattr(anilist, "anilist_id", fake_anilist_id)
    monkeypatch.setattr(reanime, "get_json", lambda key: _async(memory_cache.get(key)))
    monkeypatch.setattr(reanime, "set_json", lambda key, value, ttl: _async(None))
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
