from __future__ import annotations

import logging
from typing import Annotated, Any
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator

from app.auth.dependencies import get_current_user
from app.core.config import Settings, get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


class AuthorizationCodeExchange(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    redirect_uri: str = Field(min_length=1, max_length=2048)
    code_verifier: str = Field(min_length=43, max_length=128)

    @field_validator("redirect_uri")
    @classmethod
    def validate_redirect_uri(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("redirect_uri must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("redirect_uri contains unsupported URL components")
        return value


class RefreshTokenExchange(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=16384)


def _token_endpoint(settings: Settings) -> str:
    base_url = settings.keycloak_jwks_url or settings.keycloak_issuer_url
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak is not configured",
        )
    return f"{str(base_url).rstrip('/')}/protocol/openid-connect/token"


async def _request_keycloak_token(
    form: dict[str, str],
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=15)
    try:
        response = await http_client.post(
            _token_endpoint(settings),
            data=form,
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        logger.warning("Keycloak token endpoint is unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Keycloak token endpoint is unavailable",
        ) from exc
    finally:
        if owns_client:
            await http_client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Keycloak returned an invalid token response",
        ) from exc

    if not response.is_success:
        error_code = payload.get("error") if isinstance(payload, dict) else None
        logger.warning(
            "Keycloak token request rejected: status=%s error=%s",
            response.status_code,
            error_code,
        )
        detail = "Keycloak rejected the token request"
        if isinstance(payload, dict):
            detail = payload.get("error_description") or payload.get("error") or detail
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
                if 400 <= response.status_code < 500
                else status.HTTP_502_BAD_GATEWAY
            ),
            detail=detail,
        )

    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Keycloak token response does not contain an access token",
        )
    return payload


@router.get("/auth/me")
async def get_me(
    user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, Any]:
    return {
        "sub": user.get("sub"),
        "username": user.get("preferred_username") or user.get("sub"),
        "email": user.get("email"),
        "roles": user.get("roles", []),
    }


@router.post("/auth/token")
async def exchange_authorization_code(
    body: AuthorizationCodeExchange,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    token = await _request_keycloak_token(
        {
            "grant_type": "authorization_code",
            "client_id": settings.keycloak_client_id,
            "code": body.code,
            "redirect_uri": body.redirect_uri,
            "code_verifier": body.code_verifier,
        },
        settings,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return token


@router.post("/auth/refresh")
async def exchange_refresh_token(
    body: RefreshTokenExchange,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    token = await _request_keycloak_token(
        {
            "grant_type": "refresh_token",
            "client_id": settings.keycloak_client_id,
            "refresh_token": body.refresh_token,
        },
        settings,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return token


@router.get("/auth/login")
async def login(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    if not settings.keycloak_issuer_url:
        return RedirectResponse(url="/")

    redirect_uri = str(request.base_url).rstrip("/") + "/api/auth/callback"
    params = {
        "client_id": settings.keycloak_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile email",
    }
    issuer = str(settings.keycloak_issuer_url).rstrip("/")
    auth_url = f"{issuer}/protocol/openid-connect/auth?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/auth/callback")
async def auth_callback(
    code: str | None = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> dict[str, str]:
    if not code:
        return {"error": "No authorization code"}
    return {"message": "Authorization code received", "code": code[:8] + "..."}


@router.get("/auth/logout")
async def logout(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    if settings.keycloak_issuer_url:
        issuer = str(settings.keycloak_issuer_url).rstrip("/")
        logout_url = f"{issuer}/protocol/openid-connect/logout"
        return {"logout_url": logout_url}
    return {"message": "Logout not configured"}
