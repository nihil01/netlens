import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

JWKS_CACHE_TTL = 600  # 10 minutes


async def get_jwks(issuer_url: str, app_state: Any) -> dict[str, Any]:
    cached = getattr(app_state, "jwks", None)
    cached_ts = getattr(app_state, "jwks_ts", None)

    if cached is not None and cached_ts is not None:
        if (time.monotonic() - cached_ts) < JWKS_CACHE_TTL:
            return cached

    url = f"{issuer_url.rstrip('/')}/protocol/openid-connect/certs"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url)
        response.raise_for_status()
        jwks = response.json()

    app_state.jwks = jwks
    app_state.jwks_ts = time.monotonic()
    logger.info("JWKS refreshed from %s", issuer_url)
    return jwks
