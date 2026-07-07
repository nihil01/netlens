from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.auth.dependencies import get_current_user
from app.core.config import Settings, get_settings

router = APIRouter()


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
    auth_url = f"{str(settings.keycloak_issuer_url).rstrip('/')}/protocol/openid-connect/auth?{urlencode(params)}"
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
        logout_url = f"{str(settings.keycloak_issuer_url).rstrip('/')}/protocol/openid-connect/logout"
        return {"logout_url": logout_url}
    return {"message": "Logout not configured"}
