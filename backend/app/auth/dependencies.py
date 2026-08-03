from __future__ import annotations

import logging
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError

from app.auth.jwks import get_jwks
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

bearer = HTTPBearer(auto_error=False)


def _invalid_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_access_token(
    token: str,
    jwks: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        jwks,
        algorithms=["RS256"],
        issuer=str(settings.keycloak_issuer_url).rstrip("/"),
        options={"verify_at_hash": False, "verify_aud": False},
    )

    _validate_access_token_claims(payload, settings)
    return payload


def _validate_access_token_claims(payload: dict[str, Any], settings: Settings) -> None:
    token_type = payload.get("typ")
    if token_type is not None and str(token_type).lower() not in {"bearer", "at+jwt"}:
        raise JWTClaimsError("Token is not an access token")

    audience_claim = payload.get("aud", [])
    if isinstance(audience_claim, str):
        audiences = {audience_claim}
    elif isinstance(audience_claim, list):
        audiences = {str(value) for value in audience_claim}
    else:
        audiences = set()

    expected_audience = settings.keycloak_audience
    authorized_party = payload.get("azp")
    audience_matches = expected_audience in audiences
    first_party_client_matches = (
        expected_audience == settings.keycloak_client_id
        and authorized_party == settings.keycloak_client_id
    )
    if not audience_matches and not first_party_client_matches:
        raise JWTClaimsError("Invalid audience")


def _extract_roles(payload: dict[str, Any], client_id: str) -> list[str]:
    realm_access = payload.get("realm_access")
    resource_access = payload.get("resource_access")
    realm_roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    client_access = resource_access.get(client_id, {}) if isinstance(resource_access, dict) else {}
    client_roles = client_access.get("roles", []) if isinstance(client_access, dict) else []
    if not isinstance(realm_roles, list):
        realm_roles = []
    if not isinstance(client_roles, list):
        client_roles = []
    return list(dict.fromkeys([*realm_roles, *client_roles]))


def _jwks_contains_kid(jwks: dict[str, Any], kid: str | None) -> bool:
    return bool(kid) and any(key.get("kid") == kid for key in jwks.get("keys", []))


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    if not settings.auth_enabled:
        return {"sub": "local-dev", "preferred_username": "local-dev", "roles": ["admin"]}

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not settings.keycloak_issuer_url:
        raise HTTPException(status_code=500, detail="KEYCLOAK_ISSUER_URL is not configured")

    try:
        # Tokens use the public browser-facing issuer, while containers fetch
        # signing keys over the private Compose network.
        jwks_source = settings.keycloak_jwks_url or settings.keycloak_issuer_url
        jwks = await get_jwks(str(jwks_source), request.app.state)
        token_header = jwt.get_unverified_header(credentials.credentials)
        try:
            payload = _decode_access_token(credentials.credentials, jwks, settings)
        except (ExpiredSignatureError, JWTClaimsError):
            raise
        except JWTError:
            if _jwks_contains_kid(jwks, token_header.get("kid")):
                raise
            refreshed_jwks = await get_jwks(
                str(jwks_source),
                request.app.state,
                force_refresh=True,
            )
            payload = _decode_access_token(
                credentials.credentials,
                refreshed_jwks,
                settings,
            )
    except httpx.HTTPError as exc:
        logger.warning("Keycloak JWKS endpoint is unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider is unavailable",
        ) from exc
    except JWTError as exc:
        try:
            claims = jwt.get_unverified_claims(credentials.credentials)
            header = jwt.get_unverified_header(credentials.credentials)
        except JWTError:
            claims = {}
            header = {}
        logger.warning(
            "JWT rejected: reason=%s kid=%s issuer=%s audience=%s authorized_party=%s",
            type(exc).__name__,
            header.get("kid"),
            claims.get("iss"),
            claims.get("aud"),
            claims.get("azp"),
        )
        raise _invalid_token() from exc

    payload["roles"] = _extract_roles(payload, settings.keycloak_client_id)
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


def require_any_role(*allowed_roles: str) -> Any:
    async def _check(user: Annotated[dict, Depends(get_current_user)]) -> dict:
        if not set(user.get("roles", [])) & set(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(allowed_roles)}",
            )
        return user

    return _check
