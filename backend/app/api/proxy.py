import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

from app.core import http as shared_http
from app.services.proxy import InvalidToken, is_playlist, rewrite_playlist, unsign

router = APIRouter(tags=["proxy"])

PASSTHROUGH_HEADERS = ("content-type", "content-length", "content-range", "accept-ranges")
MAX_PLAYLIST_BYTES = 5_000_000

_client: httpx.AsyncClient | None = None


def http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = shared_http.new(
            timeout=httpx.Timeout(30, connect=10), follow_redirects=True, max_redirects=5
        )
    return _client


@router.get("/proxy")
async def proxy(t: str, request: Request):
    try:
        url, headers = unsign(t)
    except InvalidToken as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from e

    upstream_headers = {"Accept-Encoding": "identity", **headers}
    if "range" in request.headers:
        upstream_headers["Range"] = request.headers["range"]

    client = http_client()
    try:
        upstream = await client.send(
            client.build_request("GET", url, headers=upstream_headers), stream=True
        )
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Upstream failed: {e}") from e

    if upstream.status_code >= 400:
        await upstream.aclose()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Upstream {upstream.status_code}")

    final_url = str(upstream.url)
    chunks = upstream.aiter_raw()
    first = await anext(chunks, b"")
    if is_playlist(
        final_url, upstream.headers.get("content-type", "")
    ) or first.lstrip().startswith(b"#EXTM3U"):
        body = bytearray(first)
        async for chunk in chunks:
            body += chunk
            if len(body) > MAX_PLAYLIST_BYTES:
                await upstream.aclose()
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Playlist too large")
        await upstream.aclose()
        text = rewrite_playlist(body.decode("utf-8", errors="replace"), final_url, headers)
        return Response(
            text,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-store"},
        )

    async def body_stream():
        yield first
        async for chunk in chunks:
            yield chunk

    return StreamingResponse(
        body_stream(),
        status_code=upstream.status_code,
        headers={k: v for k in PASSTHROUGH_HEADERS if (v := upstream.headers.get(k))},
        background=BackgroundTask(upstream.aclose),
    )
