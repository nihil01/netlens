"""Redis-backed fixed-window API rate limiting with fail-open degradation."""

from __future__ import annotations

import hashlib
import logging
import time

import redis.asyncio as redis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import Settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings
        self.client = (
            redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1)
            if settings.redis_url
            else None
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.settings.rate_limit_enabled or self.client is None:
            return await call_next(request)
        limit = self._limit(request.url.path)
        window = int(time.time() // 60)
        identity = self._identity(request)
        key = f"netlens:ratelimit:{window}:{identity}:{self._bucket(request.url.path)}"
        try:
            pipeline = self.client.pipeline(transaction=True)
            pipeline.incr(key)
            pipeline.expire(key, 90)
            count, _ = await pipeline.execute()
            if int(count) > limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"Retry-After": "60"},
                )
        except Exception as exc:
            logger.warning("Rate limiter unavailable: %s", type(exc).__name__)
        return await call_next(request)

    def _limit(self, path: str) -> int:
        if (
            path.endswith("/export")
            or path.endswith("/refresh")
            or path.endswith("/auth/token")
        ):
            return max(1, self.settings.rate_limit_sensitive_requests_per_minute)
        return max(1, self.settings.rate_limit_requests_per_minute)

    @staticmethod
    def _bucket(path: str) -> str:
        if path.endswith("/export"):
            return "export"
        if path.endswith("/refresh"):
            return "refresh"
        if path.endswith("/auth/token"):
            return "auth-token"
        return "api"

    @staticmethod
    def _identity(request: Request) -> str:
        authorization = request.headers.get("Authorization", "")
        if authorization:
            return hashlib.sha256(authorization.encode()).hexdigest()[:24]
        client = request.client.host if request.client else "unknown"
        return hashlib.sha256(client.encode()).hexdigest()[:24]
