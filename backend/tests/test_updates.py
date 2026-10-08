import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.anyio


async def test_the_desktop_release_is_served(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "releases_dir", str(tmp_path))
    assert (await client.get("/updates")).json() == {"version": None, "platforms": []}
    (tmp_path / "latest.yml").write_text(
        "version: 0.2.0\nfiles:\n  - url: NotFlix-Setup-0.2.0.exe\npath: NotFlix-Setup-0.2.0.exe\n"
    )
    (tmp_path / "NotFlix-Setup-0.2.0.exe").write_bytes(b"MZ" + b"\0" * 100)
    assert (await client.get("/updates")).json() == {"version": "0.2.0", "platforms": ["windows"]}
    yml = await client.get("/updates/latest.yml")
    assert yml.status_code == 200 and "0.2.0" in yml.text
    exe = await client.get("/updates/NotFlix-Setup-0.2.0.exe", headers={"range": "bytes=0-1"})
    assert exe.status_code == 206 and exe.content == b"MZ"  # ranges: differential downloads
    assert (await client.get("/updates/latest-mac.yml")).status_code == 404
    assert (await client.get("/updates/..%2Fapp%2Fmain.py")).status_code == 404


async def test_updates_need_the_api_key(client, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as bare:
        assert (await bare.get("/updates/latest.yml")).status_code == 401
