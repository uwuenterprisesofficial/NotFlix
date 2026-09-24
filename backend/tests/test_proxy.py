from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.api import proxy as proxy_api
from app.api.deps import current_user_optional
from app.main import app
from app.providers import base as providers_base
from app.providers.base import Resolved, SourceOption, Stream, Subtitle
from app.services.proxy import InvalidToken, rewrite_playlist, sign, unsign

pytestmark = pytest.mark.anyio

HEADERS = {"Referer": "https://site.example/"}


def _target(proxied: str) -> tuple[str, dict[str, str]]:
    assert proxied.startswith("/api/proxy?t=")
    return unsign(parse_qs(urlsplit(proxied).query)["t"][0])


def test_token_roundtrip_and_tampering():
    token = sign("https://cdn.example/a.m3u8", HEADERS)
    assert unsign(token) == ("https://cdn.example/a.m3u8", HEADERS)
    with pytest.raises(InvalidToken):
        unsign(token[:-2] + "xx")
    with pytest.raises(InvalidToken):
        unsign(sign("file:///etc/passwd", {}))


def test_rewrite_playlist_proxies_every_uri():
    playlist = "\n".join(
        [
            "#EXTM3U",
            '#EXT-X-KEY:METHOD=AES-128,URI="key.bin",IV=0x1',
            '#EXT-X-MAP:URI="/init.mp4"',
            "#EXTINF:4.0,",
            "seg-1.ts",
            "",
            "#EXTINF:4.0,",
            "https://other.example/seg-2.ts?sig=1",
            "#EXT-X-ENDLIST",
        ]
    )
    lines = rewrite_playlist(playlist, "https://cdn.example/hls/720/index.m3u8", HEADERS).split(
        "\n"
    )
    assert lines[0] == "#EXTM3U"
    key_uri = lines[1].split('URI="')[1].split('"')[0]
    assert _target(key_uri) == ("https://cdn.example/hls/720/key.bin", HEADERS)
    assert lines[1].endswith(",IV=0x1")
    assert _target(lines[2].split('URI="')[1].rstrip('"'))[0] == "https://cdn.example/init.mp4"
    assert _target(lines[4])[0] == "https://cdn.example/hls/720/seg-1.ts"
    assert _target(lines[7])[0] == "https://other.example/seg-2.ts?sig=1"
    assert lines[8] == "#EXT-X-ENDLIST"


@pytest.fixture
def upstream(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/master":  # a playlist without .m3u8 or a playlist MIME type
            return httpx.Response(200, stream=httpx.ByteStream(b"#EXTM3U\nlow/index.m3u8\n"))
        if request.url.path == "/video.mp4":
            return httpx.Response(
                206,
                stream=httpx.ByteStream(b"abcd"),
                headers={"content-type": "video/mp4", "content-range": "bytes 0-3/10"},
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(proxy_api, "_client", client)
    return seen


async def test_proxy_rewrites_playlists_and_forwards_headers(client, upstream):
    resp = await client.get("/proxy", params={"t": sign("https://cdn.example/master", HEADERS)})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.apple.mpegurl"
    variant = resp.text.splitlines()[1]
    assert _target(variant) == ("https://cdn.example/low/index.m3u8", HEADERS)
    assert upstream[0].headers["referer"] == "https://site.example/"


async def test_proxy_streams_media_with_ranges(client, upstream):
    token = sign("https://cdn.example/video.mp4", {})
    resp = await client.get("/proxy", params={"t": token}, headers={"Range": "bytes=0-3"})
    assert resp.status_code == 206
    assert resp.content == b"abcd"
    assert resp.headers["content-range"] == "bytes 0-3/10"
    assert upstream[0].headers["range"] == "bytes=0-3"


async def test_proxy_rejects_bad_tokens_and_upstream_errors(client, upstream):
    assert (await client.get("/proxy", params={"t": "nope"})).status_code == 403
    missing = sign("https://cdn.example/missing", {})
    assert (await client.get("/proxy", params={"t": missing})).status_code == 502


class FakeProvider:
    name = "fake"

    async def options(self, anime, episode):
        return [SourceOption(id="fake:hd", provider="fake", label="Fake", language="en-sub")]

    async def resolve(self, anime, episode, key):
        return Resolved(
            streams=[
                Stream(
                    kind="direct",
                    url="https://cdn.example/master.m3u8",
                    label="HD",
                    format="hls",
                    headers=HEADERS,
                    subtitles=(Subtitle(url="https://cdn.example/en.vtt", label="English"),),
                ),
                Stream(
                    kind="direct", url="https://cdn.example/plain.mp4", label="MP4", format="file"
                ),
            ]
        )


async def test_resolved_streams_are_proxied_when_needed(client, monkeypatch):
    monkeypatch.setattr(providers_base, "enabled_providers", lambda: [FakeProvider()])
    [option] = (await client.get("/anime/9/episodes/1/sources")).json()
    assert option == {
        "id": "fake:hd",
        "provider": "fake",
        "label": "Fake",
        "language": "en-sub",
        "resolved": None,
    }

    body = (await client.get("/anime/9/episodes/1/resolve", params={"option": "fake:hd"})).json()
    hls, mp4 = body["streams"]
    assert _target(hls["url"]) == ("https://cdn.example/master.m3u8", HEADERS)
    assert _target(hls["subtitles"][0]["url"])[0] == "https://cdn.example/en.vtt"
    assert mp4["url"] == "https://cdn.example/plain.mp4"

    unknown = await client.get("/anime/9/episodes/1/resolve", params={"option": "nope:x"})
    assert unknown.status_code == 404


async def test_aniworld_mapping_override(client, user):
    from app.services.mappings import delete_mapping

    await delete_mapping(9, "aniworld")
    app.dependency_overrides.pop(current_user_optional)
    body = {"slug": "one-piece", "season": 2, "episode_offset": 10}
    assert (await client.put("/anime/9/mappings/aniworld", json=body)).status_code == 401

    app.dependency_overrides[current_user_optional] = lambda: user
    bad = await client.put("/anime/9/mappings/aniworld", json={"slug": "../x", "season": 1})
    assert bad.status_code == 422
    assert (await client.put("/anime/9/mappings/aniworld", json=body)).status_code == 204
    [mapping] = (await client.get("/anime/9/mappings")).json()
    assert mapping == {
        "provider": "aniworld",
        "external_id": "one-piece",
        "season": 2,
        "episode_offset": 10,
        "manual": True,
    }
    assert (await client.delete("/anime/9/mappings/aniworld")).status_code == 204
    assert (await client.get("/anime/9/mappings")).json() == []


class EmbedOnlyProvider(FakeProvider):
    async def resolve(self, anime, episode, key):
        return Resolved(streams=[Stream(kind="embed", url="https://embed.example", label="E")])


def test_analyzer_uses_direct_provider_streams(database, monkeypatch, tmp_path):
    from app.analysis.media import MediaNotFound, resolve_all
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "media_dir", str(tmp_path))
    (tmp_path / "9").mkdir()
    (tmp_path / "9" / "1.mkv").write_bytes(b"")

    monkeypatch.setattr(providers_base, "enabled_providers", lambda: [FakeProvider()])
    media = resolve_all(9, [1, 2])
    assert media[1].source == str(tmp_path / "9" / "1.mkv")
    assert (media[2].source, media[2].headers) == ("https://cdn.example/master.m3u8", HEADERS)

    monkeypatch.setattr(providers_base, "enabled_providers", lambda: [EmbedOnlyProvider()])
    with pytest.raises(MediaNotFound, match="episode 2"):
        resolve_all(9, [1, 2])
