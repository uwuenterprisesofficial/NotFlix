"""Watch Together rooms: one per connection, holding what the pair is watching and where.

The state lives in Redis (so every API process sees it) and each change is published on the
room's channel, which the players follow through server-sent events (`events`):

    {rev, anime_id, episode, title, position, playing, at, by, action, stream}

`position` is where playback was at `at` (server time, ms); while `playing` it moves on in
real time, so a player computes where it should be from the server's clock. Changes are
last-writer-wins, ordered by `rev`: a change is only stored (and published) when it's newer
than the stored one.

Who has the room open (and where) is kept per user with a short expiry, refreshed while their
event stream is connected.
"""

import asyncio
import json
import secrets
import time
from collections.abc import AsyncIterator
from typing import Any

import anyio

from app.core.cache import redis

ROOM_TTL_S = 24 * 3600
PRESENCE_TTL_S = 45
HEARTBEAT_S = 15

# Store the state only if it's newer than the stored one, and publish it.
_SET_IF_NEWER = """
local current = redis.call('GET', KEYS[1])
if current then
  local stored = cjson.decode(current)
  if stored['rev'] >= tonumber(ARGV[2]) then return 0 end
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
redis.call('PUBLISH', KEYS[2], ARGV[4])
return 1
"""


def _state_key(connection_id: int) -> str:
    return f"together:room:{connection_id}"


def _channel(connection_id: int) -> str:
    return f"together:events:{connection_id}"


def _presence_key(connection_id: int, user_id: int) -> str:
    return f"together:presence:{connection_id}:{user_id}"


def now_ms() -> int:
    return int(time.time() * 1000)


async def state(connection_id: int) -> dict[str, Any] | None:
    raw = await redis().get(_state_key(connection_id))
    return json.loads(raw) if raw else None


def expected_position(room: dict[str, Any], at_ms: int | None = None) -> float:
    """Where playback is now (it moves on while playing)."""
    if not room["playing"]:
        return room["position"]
    return room["position"] + max(0, (at_ms or now_ms()) - room["at"]) / 1000


class Conflict(Exception):
    """The change is about another episode than the room's (the room moved on)."""

    def __init__(self, room: dict[str, Any] | None):
        self.room = room


async def update(
    connection_id: int,
    user_id: int,
    action: str,
    *,
    anime_id: int,
    episode: int,
    position: float,
    playing: bool | None = None,
    title: str | None = None,
    stream: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a change: `load` (start an episode), `play`, `pause`, `seek`, or `stream` (the
    stream changed). Returns the new state."""
    current = await state(connection_id)
    same = current is not None and (current["anime_id"], current["episode"]) == (anime_id, episode)
    if action != "load" and not same:
        raise Conflict(current)
    if action == "load":
        new_playing = bool(playing)
    elif action in ("play", "pause"):
        new_playing = action == "play"
    else:
        new_playing = current["playing"] if playing is None else playing
    rev = await redis().incr(f"together:rev:{connection_id}")
    room = {
        "rev": rev,
        "anime_id": anime_id,
        "episode": episode,
        "title": title if action == "load" or not current else (title or current.get("title")),
        "position": max(0.0, position),
        "playing": new_playing,
        "at": now_ms(),
    }
    if action == "stream":
        # Only the stream changed: playback carries on from where the room had it.
        room.update(position=current["position"], at=current["at"])
    room |= {
        "by": user_id,
        "action": action,
        "stream": stream if stream is not None else (current or {}).get("stream"),
    }
    event = json.dumps({"type": "state", "state": room, "now": room["at"]})
    await redis().eval(
        _SET_IF_NEWER, 2, _state_key(connection_id), _channel(connection_id),
        json.dumps(room), rev, ROOM_TTL_S, event,
    )  # fmt: skip
    return room


async def clear(connection_id: int) -> None:
    await redis().delete(_state_key(connection_id), f"together:rev:{connection_id}")


async def presence(connection_id: int, user_ids: list[int]) -> list[dict[str, Any]]:
    """Who has the room open: [{user_id, anime_id, episode}] (anime/episode on a watch page)."""
    raw = await redis().mget([_presence_key(connection_id, u) for u in user_ids])
    entries = [json.loads(r) for r in raw if r]
    return [{k: v for k, v in e.items() if k != "token"} for e in entries]


async def _set_presence(connection_id: int, entry: dict[str, Any]) -> None:
    await redis().set(
        _presence_key(connection_id, entry["user_id"]), json.dumps(entry), ex=PRESENCE_TTL_S
    )


async def _publish_presence(connection_id: int, user_ids: list[int]) -> None:
    members = await presence(connection_id, user_ids)
    await redis().publish(
        _channel(connection_id),
        json.dumps({"type": "presence", "members": members, "now": now_ms()}),
    )


def _sse(data: str) -> str:
    return f"data: {data}\n\n"


async def events(
    connection_id: int,
    user_id: int,
    user_ids: list[int],
    anime_id: int | None = None,
    episode: int | None = None,
) -> AsyncIterator[str]:
    """The room's server-sent events for one open player (or Together page): the current state
    and who's there first, then every change, and a comment line every little while to keep
    proxies from closing the connection."""
    token = secrets.token_hex(8)
    entry = {"user_id": user_id, "anime_id": anime_id, "episode": episode, "token": token}
    pubsub = redis().pubsub()
    await pubsub.subscribe(_channel(connection_id))
    try:
        await _set_presence(connection_id, entry)
        await _publish_presence(connection_id, user_ids)
        yield "retry: 2000\n\n"
        room = await state(connection_id)
        yield _sse(json.dumps({"type": "state", "state": room, "now": now_ms()}))
        members = await presence(connection_id, user_ids)
        yield _sse(json.dumps({"type": "presence", "members": members, "now": now_ms()}))
        beat = time.monotonic()
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is not None:
                data = message["data"]
                yield _sse(data.decode() if isinstance(data, bytes) else data)
            if time.monotonic() - beat >= HEARTBEAT_S:
                beat = time.monotonic()
                await _set_presence(connection_id, entry)
                yield f": ping {now_ms()}\n\n"
            await asyncio.sleep(0)
    finally:
        # The client went away: the stream is being cancelled, so shield the clean-up.
        with anyio.CancelScope(shield=True):
            key = _presence_key(connection_id, user_id)
            stored = await redis().get(key)
            # Only this stream's entry: the same user may have the room open in another tab.
            if stored and json.loads(stored).get("token") == token:
                await redis().delete(key)
            await pubsub.unsubscribe()
            await pubsub.aclose()
            await _publish_presence(connection_id, user_ids)
