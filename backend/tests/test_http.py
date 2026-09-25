import asyncio

import pytest

from app.core import http

pytestmark = pytest.mark.anyio


async def test_shared_clients_honour_proxy_settings(monkeypatch):
    # A custom transport would make httpx ignore these: outside services became unreachable
    # wherever a proxy is needed (e.g. AniList, which Anivexa needs for its ids).
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    client = http.shared("proxy-test")
    assert any(
        getattr(transport, "_pool", None) is not None
        and "proxy" in type(transport._pool).__name__.lower()
        for transport in client._mounts.values()
        if transport is not None
    )


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_a_dropped_connection_is_retried_once(method):
    seen = []

    async def handle(reader, writer):
        seen.append(1)
        head = await reader.readuntil(b"\r\n\r\n")
        length = [ln for ln in head.split(b"\r\n") if ln.lower().startswith(b"content-length")]
        if length:
            await reader.readexactly(int(length[0].split(b":")[1]))
        if len(seen) == 1:  # the first connection closes without an answer
            writer.close()
            return
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        client = http.shared(f"retry-{method}", trust_env=False)
        resp = await client.request(method, f"http://127.0.0.1:{port}/", json={"q": 1})
    assert resp.text == "ok" and len(seen) == 2
