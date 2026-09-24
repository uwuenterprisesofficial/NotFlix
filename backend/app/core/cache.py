import json
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings

_redis: Redis | None = None


def redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url)
    return _redis


async def get_json(key: str) -> Any | None:
    raw = await redis().get(key)
    return json.loads(raw) if raw is not None else None


async def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    await redis().set(key, json.dumps(value), ex=ttl_seconds)


async def close() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
