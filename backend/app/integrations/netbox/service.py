import ipaddress
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.ip_intelligence.schemas import IntegrationStatus, NetBoxContext


class NetBoxService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @classmethod
    def from_settings(cls) -> "NetBoxService":
        return cls(get_settings())

    async def lookup_ip(self, ip: str) -> NetBoxContext:
        if not self.settings.netbox_url or not self.settings.netbox_token:
            return NetBoxContext(
                known=False,
                status=IntegrationStatus(
                    status="not_configured",
                    message="NETBOX_URL and NETBOX_TOKEN are required",
                ),
            )

        try:
            async with self._client() as client:
                ip_object = await self._find_ip_address(client, ip)
                if not ip_object:
                    return NetBoxContext(known=False)

                assigned = ip_object.get("assigned_object") or {}
                device = self._extract_device(assigned)
                interfaces = []
                if device and device.get("id"):
                    interfaces = await self._fetch_device_interfaces(client, int(device["id"]))

                return self._map_context(ip_object, device, interfaces)
        except httpx.HTTPError as exc:
            return NetBoxContext(
                known=False,
                status=IntegrationStatus(status="error", message=f"NetBox HTTP error: {exc}"),
            )
        except Exception as exc:  # defensive boundary: API shape differs by NetBox version
            return NetBoxContext(
                known=False,
                status=IntegrationStatus(status="error", message=f"NetBox mapping error: {exc}"),
            )

    def _client(self) -> httpx.AsyncClient:
        headers = {
            "Authorization": f"Token {self.settings.netbox_token}",
            "Accept": "application/json",
        }
        return httpx.AsyncClient(
            base_url=str(self.settings.netbox_url).rstrip("/"),
            headers=headers,
            verify=self.settings.netbox_verify_ssl,
            timeout=self.settings.netbox_timeout_seconds,
        )

    async def _find_ip_address(self, client: httpx.AsyncClient, ip: str) -> dict[str, Any] | None:
        response = await client.get("/api/ipam/ip-addresses/", params={"q": ip, "limit": 10})
        response.raise_for_status()
        results = response.json().get("results", [])
        for item in results:
            if self._address_without_prefix(item.get("address")) == ip:
                return item

        # Exact /32 and /128 fallbacks help when NetBox search is restricted.
        address = f"{ip}/32" if ipaddress.ip_address(ip).version == 4 else f"{ip}/128"
        response = await client.get(
            "/api/ipam/ip-addresses/",
            params={"address": address, "limit": 1},
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return results[0] if results else None

    async def _fetch_device_interfaces(
        self, client: httpx.AsyncClient, device_id: int
    ) -> list[dict[str, Any]]:
        response = await client.get(
            "/api/dcim/interfaces/",
            params={"device_id": device_id, "limit": 100},
        )
        response.raise_for_status()
        interfaces = []
        for item in response.json().get("results", []):
            interfaces.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": self._display(item.get("type")),
                    "enabled": item.get("enabled"),
                    "mac_address": item.get("mac_address"),
                    "description": item.get("description"),
                    "mode": self._display(item.get("mode")),
                    "untagged_vlan": self._nested_name(item.get("untagged_vlan")),
                }
            )
        return interfaces

    def _map_context(
        self,
        ip_object: dict[str, Any],
        device: dict[str, Any] | None,
        interfaces: list[dict[str, Any]],
    ) -> NetBoxContext:
        if not device:
            return NetBoxContext(known=True, interfaces=interfaces)

        site = device.get("site") or {}
        region = site.get("region") or {}
        location = device.get("location") or {}
        role = device.get("role") or device.get("device_role") or {}

        return NetBoxContext(
            known=True,
            device=device.get("name"),
            site=site.get("name"),
            region=region.get("name"),
            city=location.get("name") or site.get("physical_address") or site.get("name"),
            role=role.get("name"),
            interfaces=interfaces,
        )

    @staticmethod
    def _extract_device(assigned: dict[str, Any]) -> dict[str, Any] | None:
        if not assigned:
            return None
        if assigned.get("device"):
            return assigned["device"]
        if assigned.get("virtual_machine"):
            vm = assigned["virtual_machine"]
            return {**vm, "role": {"name": "virtual-machine"}}
        return None

    @staticmethod
    def _address_without_prefix(address: str | None) -> str | None:
        return address.split("/", 1)[0] if address else None

    @staticmethod
    def _display(value: Any) -> str | None:
        if isinstance(value, dict):
            return value.get("label") or value.get("value") or value.get("name")
        return value

    @staticmethod
    def _nested_name(value: Any) -> str | None:
        return value.get("name") if isinstance(value, dict) else None
