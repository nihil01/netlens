from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.auth.jwks import get_jwks
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    if not settings.auth_enabled:
        return {"sub": "local-dev", "preferred_username": "local-dev", "roles": ["admin"]}

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    if not settings.keycloak_issuer_url:
        raise HTTPException(status_code=500, detail="KEYCLOAK_ISSUER_URL is not configured")

    try:
        jwks = await get_jwks(str(settings.keycloak_issuer_url), request.app.state)

        # Debug: decode without validation first
        try:
            unverified = jwt.get_unverified_claims(credentials.credentials)
            logger.info("Token claims - sub: %s, aud: %s, exp: %s, iss: %s",
                       unverified.get("sub"), unverified.get("aud"),
                       unverified.get("exp"), unverified.get("iss"))
        except Exception as e:
            logger.error("Cannot decode token: %s", e)

        payload = jwt.decode(
            credentials.credentials,
            jwks,
            algorithms=["RS256"],
            audience=settings.keycloak_audience,
            issuer=str(settings.keycloak_issuer_url).rstrip("/"),
            options={"verify_at_hash": False},
        )
        logger.info("Token decoded successfully for user: %s", payload.get("preferred_username"))
    except JWTError as exc:
        logger.error("JWT validation failed: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    realm_roles = payload.get("realm_access", {}).get("roles", [])
    payload["roles"] = realm_roles
    return payload


def require_role(*required_roles: str) -> Any:
    async def _check(user: Annotated[dict, Depends(get_current_user)]) -> dict:
        user_roles = set(user.get("roles", []))
        if not set(required_roles).issubset(user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires roles: {', '.join(required_roles)}",
            )
        return user
    return _check
