import logging
from datetime import datetime
from typing import Any

from app.cache.redis_cache import JsonRedisCache

SCANNER_PROFILES_CACHE_KEY = "scanner:profiles:latest"
logger = logging.getLogger(__name__)


class ScannerProfileStore:
    def __init__(self, cache: JsonRedisCache | None = None) -> None:
        self.cache = cache or JsonRedisCache()

    async def save(
        self,
        profiles: list[dict[str, Any]],
        *,
        trigger: str,
        started_at: datetime,
        finished_at: datetime,
    ) -> dict[str, Any]:
        payload = {
            "status": "ready",
            "trigger": trigger,
            "started_at": started_at.isoformat(),
            "updated_at": finished_at.isoformat(),
            "hosts_total": len(profiles),
            "profiles": profiles,
        }
        await self.cache.set_json(SCANNER_PROFILES_CACHE_KEY, payload)
        return payload

    async def get_latest(self) -> dict[str, Any]:
        try:
            cached = await self.cache.get_json(SCANNER_PROFILES_CACHE_KEY)
        except Exception:
            logger.exception("Unable to read scanner profiles from Redis")
            cached = None
        if isinstance(cached, dict):
            return cached
        return {
            "status": "unavailable",
            "trigger": None,
            "started_at": None,
            "updated_at": None,
            "hosts_total": 0,
            "profiles": [],
        }
