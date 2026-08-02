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

    async def get_json(self, key: str) -> Any | None:
        if not self.client:
            return None

        raw = await self.client.get(key)
        if not raw:
            return None

        return json.loads(raw)

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        if not self.client:
            logger.debug("redis client is disabled")
            return

        logger.debug("redis set: %s ttl: %s", key, ttl_seconds)

        result = await self.client.set(
            key,
            json.dumps(value, ensure_ascii=False),
            ex=ttl_seconds,
        )

        logger.debug("redis set result: %s", result)

    async def delete(self, key: str) -> int:
        if self.client:
            return int(await self.client.delete(key))
        return 0

    async def delete_prefix(self, prefix: str) -> int:
        """Delete only keys owned by one integration, without flushing Redis."""
        if not self.client:
            return 0
        deleted = 0
        batch: list[str] = []
        async for key in self.client.scan_iter(match=f"{prefix}*"):
            batch.append(str(key))
            if len(batch) >= 100:
                deleted += int(await self.client.delete(*batch))
                batch.clear()
        if batch:
            deleted += int(await self.client.delete(*batch))
        return deleted

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()
