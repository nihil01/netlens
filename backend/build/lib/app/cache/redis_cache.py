import json
import logging
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class JsonRedisCache:
    def __init__(self) -> None:

        self.settings = get_settings()
        self.enabled = bool(self.settings.redis_url)
        self.client: redis.Redis | None = None

        if self.enabled:
            logger.info("enable redis cache")
            self.client = redis.from_url(
                self.settings.redis_url,
                decode_responses=True,
            )

    async def get_json(self, key: str) -> dict[str, Any] | None:
        if not self.client:
            return None

        raw = await self.client.get(key)
        if not raw:
            return None

        return json.loads(raw)

    async def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        if not self.client:
            logger.debug("redis client is disabled")
            return

        logger.debug("redis set: %s ttl: %d", key, ttl_seconds)

        result = await self.client.set(
            key,
            json.dumps(value, ensure_ascii=False),
            ex=ttl_seconds,
        )

        logger.debug("redis set result: %s", result)

    async def delete(self, key: str) -> None:
        if self.client:
            await self.client.delete(key)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()