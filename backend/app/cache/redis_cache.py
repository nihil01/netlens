import json
from typing import Any

import redis.asyncio as redis


class JsonRedisCache:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url

    async def get_json(self, key: str) -> dict[str, Any] | None:
        client = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        try:
            value = await client.get(key)
        finally:
            await client.aclose()
        if value is None:
            return None
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else None

    async def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        client = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        try:
            await client.set(key, json.dumps(value, default=str), ex=ttl_seconds)
        finally:
            await client.aclose()
