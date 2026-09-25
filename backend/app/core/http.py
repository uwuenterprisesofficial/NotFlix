"""Shared outgoing HTTP clients.

Creating an httpx client is expensive (it loads the CA bundle into a new TLS context: tens of
milliseconds), and a client per call opens a new connection and TLS handshake every time. So
each service (MAL, AniList, ...) gets one long-lived client with a connection pool, and every
other client reuses one TLS context.

Clients belong to an event loop (tests run one per test), so they're kept per loop.
"""

import asyncio
import ssl
from functools import cache

import httpx

_clients: dict[str, tuple[asyncio.AbstractEventLoop, httpx.AsyncClient]] = {}


@cache
def ssl_context() -> ssl.SSLContext:
    """One TLS context (as httpx makes it, honouring SSL_CERT_FILE etc.) for every client."""
    return httpx.create_ssl_context()


def shared(name: str, timeout: httpx.Timeout | float = 20, **kwargs) -> httpx.AsyncClient:
    """The long-lived client for a service. Don't close it (it's used by everyone)."""
    loop = asyncio.get_running_loop()
    found = _clients.get(name)
    if found is not None and found[0] is loop and not found[1].is_closed:
        return found[1]
    client = httpx.AsyncClient(
        timeout=timeout,
        verify=ssl_context(),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60),
        **kwargs,
    )
    _clients[name] = (loop, client)
    return client


def new(timeout: httpx.Timeout | float = 20, **kwargs) -> httpx.AsyncClient:
    """A client of its own (e.g. with cookies or special settings), sharing the TLS context."""
    return httpx.AsyncClient(timeout=timeout, verify=ssl_context(), **kwargs)


async def close_all() -> None:
    for loop, client in list(_clients.values()):
        if loop is asyncio.get_running_loop():
            await client.aclose()
    _clients.clear()
