"""Safe, read-only FMC aggregate-metrics diagnostic.

Credentials are loaded through :class:`Settings`. Tokens and response bodies are never
printed. Set ``FMC_TEST_DEVICE`` to target one UUID; otherwise the first discovered
device is used.
"""
from __future__ import annotations

import asyncio
import os
from urllib.parse import quote

import httpx

from app.core.config import Settings


async def main() -> None:
    settings = Settings()
    if not (settings.fmc_url and settings.fmc_username and settings.fmc_password):
        raise SystemExit("FMC_URL, FMC_USERNAME and FMC_PASSWORD must be configured")

    base = settings.fmc_url.rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]

    async with httpx.AsyncClient(
        verify=settings.fmc_verify_ssl,
        timeout=settings.fmc_timeout_seconds,
    ) as client:
        auth = await client.post(
            f"{base}/api/fmc_platform/v1/auth/generatetoken",
            auth=httpx.BasicAuth(settings.fmc_username, settings.fmc_password),
        )
        auth.raise_for_status()
        token = auth.headers.get("X-auth-access-token", "")
        domain = auth.headers.get("DOMAIN_UUID", "")
        if not token or not domain:
            raise SystemExit("FMC authentication response omitted token or domain UUID")

        headers = {"X-auth-access-token": token, "Accept": "application/json"}
        discovery_url = (
            f"{base}/api/fmc_config/v1/domain/{domain}/devices/devicerecords"
            "?offset=0&limit=1000&expanded=true"
        )
        discovery = await client.get(discovery_url, headers=headers)
        discovery.raise_for_status()
        devices = discovery.json().get("items", [])
        requested_id = os.getenv("FMC_TEST_DEVICE")
        device = next((item for item in devices if item.get("id") == requested_id), None)
        if device is None:
            device = next((item for item in devices if item.get("id")), None)
        if device is None:
            raise SystemExit("FMC discovery returned no device with an ID")

        device_id = device["id"]
        aggregate_url = (
            f"{base}/api/fmc_config/v1/domain/{domain}/health/aggregatemetrics"
            f"?filter={quote(f'device_uuid:{device_id}')}&expanded=true"
        )
        started = asyncio.get_running_loop().time()
        response = await client.get(aggregate_url, headers=headers)
        duration_ms = round((asyncio.get_running_loop().time() - started) * 1000, 1)

        items: list[dict] = []
        if response.status_code == 200:
            try:
                items = response.json().get("items", [])
            except ValueError:
                pass
        blocks = sorted(
            key
            for key in (items[-1] if items else {})
            if key.endswith("HealthMetrics") or key.endswith("HealthMetricsList")
        )
        print(
            {
                "device_id": device_id,
                "device_name": device.get("name"),
                "model": device.get("model"),
                "connected": device.get("isConnected"),
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "response_bytes": len(response.content),
                "items_count": len(items),
                "metric_blocks": blocks,
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
