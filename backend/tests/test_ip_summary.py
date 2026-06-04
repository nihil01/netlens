from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_ip_summary_contract_when_integrations_are_not_configured() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/ip/10.255.127.60/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["ip"] == "10.255.127.60"
    assert body["netbox"]["known"] is False
    assert body["netbox"]["status"]["status"] == "not_configured"
    assert body["activity"]["status"]["status"] == "not_configured"


async def test_ip_summary_rejects_invalid_ip() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/ip/not-an-ip/summary")

    assert response.status_code == 422
