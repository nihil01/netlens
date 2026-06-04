from typing import Any

import httpx


async def get_jwks(issuer_url: str, app_state: Any) -> dict[str, Any]:
    cached = getattr(app_state, "jwks", None)
    if cached:
        return cached

    url = f"{issuer_url.rstrip('/')}/protocol/openid-connect/certs"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url)
        response.raise_for_status()
        jwks = response.json()

    app_state.jwks = jwks
    return jwks
