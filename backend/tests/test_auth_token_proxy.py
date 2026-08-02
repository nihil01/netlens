from urllib.parse import parse_qs

import httpx
import pytest
from fastapi import HTTPException

from app.api.routes.auth import AuthorizationCodeExchange, _request_keycloak_token
from app.core.config import Settings


def auth_settings() -> Settings:
    return Settings(
        keycloak_issuer_url="http://public-keycloak:8080/realms/dvx",
        keycloak_jwks_url="http://private-keycloak:8080/realms/dvx",
        keycloak_client_id="netlens",
    )


def test_authorization_exchange_preserves_exact_redirect_uri() -> None:
    body = AuthorizationCodeExchange(
        code="authorization-code",
        redirect_uri="https://net-mgmt.taxes.gov.az:8089",
        code_verifier="a" * 43,
    )

    assert body.redirect_uri == "https://net-mgmt.taxes.gov.az:8089"


@pytest.mark.asyncio
async def test_token_proxy_uses_private_keycloak_url_and_pkce_form() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "http://private-keycloak:8080/realms/dvx/protocol/openid-connect/token"
        )
        form = parse_qs(request.content.decode())
        assert form == {
            "grant_type": ["authorization_code"],
            "client_id": ["netlens"],
            "code": ["authorization-code"],
            "redirect_uri": ["https://net-mgmt.taxes.gov.az:8089"],
            "code_verifier": ["a" * 43],
        }
        return httpx.Response(
            200,
            json={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 300,
                "token_type": "Bearer",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _request_keycloak_token(
            {
                "grant_type": "authorization_code",
                "client_id": "netlens",
                "code": "authorization-code",
                "redirect_uri": "https://net-mgmt.taxes.gov.az:8089",
                "code_verifier": "a" * 43,
            },
            auth_settings(),
            client,
        )

    assert result["access_token"] == "access-token"


@pytest.mark.asyncio
async def test_token_proxy_returns_safe_keycloak_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "Code is not valid"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as error:
            await _request_keycloak_token(
                {"grant_type": "refresh_token", "refresh_token": "expired"},
                auth_settings(),
                client,
            )

    assert error.value.status_code == 400
    assert error.value.detail == "Code is not valid"
