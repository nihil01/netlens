from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_ip_summary_mock_contract() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/ip/10.255.127.60/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["ip"] == "10.255.127.60"
    assert body["netbox"]["known"] is True
    assert body["activity"]["internal_connections"] >= 0


async def test_ip_summary_rejects_invalid_ip() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/ip/not-an-ip/summary")

    assert response.status_code == 422
