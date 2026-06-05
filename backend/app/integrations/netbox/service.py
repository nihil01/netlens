import ipaddress
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.cache.redis_cache import JsonRedisCache
from app.core.config import Settings, get_settings
from app.ip_intelligence.schemas import (
    IntegrationStatus,
    NetBoxContext,
    NetBoxDevice,
    NetBoxDeviceDetail,
    NetBoxInterface,
    NetBoxInventory,
    NetBoxRegion,
    NetBoxRegionsResponse,
    NetBoxSite,
)


class NetBoxService:
    def __init__(
        self, settings: Settings | None = None, cache: JsonRedisCache | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or JsonRedisCache(self.settings.redis_url)

    @classmethod
    def from_settings(cls) -> "NetBoxService":
        return cls(get_settings())

    def _is_configured(self) -> bool:
        return bool(self.settings.netbox_url and self.settings.netbox_token)

    async def fetch_all(self) -> NetBoxRegionsResponse:
        """Compatibility endpoint for the nested region -> site -> device tree."""
        inventory = await self.get_inventory()
        if inventory.status.status != "ok":
            return NetBoxRegionsResponse(regions=[])

        sites_by_region: dict[str, list[NetBoxSite]] = defaultdict(list)
        devices_by_site: dict[str, list[NetBoxDevice]] = defaultdict(list)
        interfaces_by_device: dict[int, list[NetBoxInterface]] = defaultdict(list)

        for interface in inventory.interfaces:
            if interface.device_id is not None:
                interfaces_by_device[interface.device_id].append(interface)

        for device in inventory.devices:
            if not device.site:
                continue
            devices_by_site[device.site].append(
                device.model_copy(update={"interfaces": interfaces_by_device[device.id]})
            )

        for site in inventory.sites:
            if not site.region:
                continue
            sites_by_region[site.region].append(
                site.model_copy(update={"devices": devices_by_site[site.name]})
            )

        regions = [
            region.model_copy(update={"sites": sites_by_region[region.name]})
            for region in inventory.regions
        ]
        return NetBoxRegionsResponse(regions=regions)

    async def lookup_ip(self, ip: str) -> NetBoxContext:
        if not self._is_configured():
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
                    device_id = int(device["id"])
                    device_interfaces = await self._fetch_device_interfaces(client, device_id)
                    interfaces = [item.model_dump() for item in device_interfaces]

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

    async def get_inventory(self) -> NetBoxInventory:
        """Live inventory lists. Keep these fresh; only heavy device details are cached."""
        if not self._is_configured():
            return NetBoxInventory(
                status=IntegrationStatus(
                    status="not_configured",
                    message="NETBOX_URL and NETBOX_TOKEN are required",
                )
            )

        try:
            async with self._client() as client:
                regions = await self._fetch_all(client, "/api/dcim/regions/", {"limit": 200})
                sites = await self._fetch_all(client, "/api/dcim/sites/", {"limit": 200})
                devices = await self._fetch_all(client, "/api/dcim/devices/", {"limit": 200})
                interfaces = await self._fetch_all(client, "/api/dcim/interfaces/", {"limit": 500})

            return NetBoxInventory(
                regions=[self._map_region(item) for item in regions],
                sites=[self._map_site(item) for item in sites],
                devices=[self._map_device(item) for item in devices],
                interfaces=[self._map_interface(item) for item in interfaces],
            )
        except httpx.HTTPError as exc:
            return NetBoxInventory(
                status=IntegrationStatus(status="error", message=f"NetBox HTTP error: {exc}")
            )
        except Exception as exc:
            return NetBoxInventory(
                status=IntegrationStatus(status="error", message=f"NetBox mapping error: {exc}")
            )

    async def get_device_detail(self, device_id: int) -> NetBoxDeviceDetail:
        cache_key = f"netbox:device:{device_id}"
        cached = await self._cache_get(cache_key)
        if cached:
            cached["cache"] = {**cached.get("cache", {}), "hit": True, "key": cache_key}
            return NetBoxDeviceDetail.model_validate(cached)

        if not self._is_configured():
            return NetBoxDeviceDetail(
                id=device_id,
                name=f"device-{device_id}",
                cache={"hit": False, "key": cache_key},
                status_meta=IntegrationStatus(
                    status="not_configured",
                    message="NETBOX_URL and NETBOX_TOKEN are required",
                ),
            )

        async with self._client() as client:
            response = await client.get(f"/api/dcim/devices/{device_id}/")
            response.raise_for_status()
            device = response.json()
            interfaces = await self._fetch_device_interfaces(client, device_id)

        detail = self._map_device_detail(device, interfaces, cache_key)
        await self._cache_set(cache_key, detail.model_dump(mode="json"))
        return detail

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

    async def _fetch_all(
        self, client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_url: str | None = path
        current_params = params or {}
        while next_url:
            response = await client.get(next_url, params=current_params)
            response.raise_for_status()
            payload = response.json()
            items.extend(payload.get("results", []))
            next_url = payload.get("next")
            current_params = {}
        return items

    async def _find_ip_address(self, client: httpx.AsyncClient, ip: str) -> dict[str, Any] | None:
        response = await client.get("/api/ipam/ip-addresses/", params={"q": ip, "limit": 10})
        response.raise_for_status()
        results = response.json().get("results", [])
        for item in results:
            if self._address_without_prefix(item.get("address")) == ip:
                return item

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
    ) -> list[NetBoxInterface]:
        response = await client.get(
            "/api/dcim/interfaces/",
            params={"device_id": device_id, "limit": 500},
        )
        response.raise_for_status()
        return [self._map_interface(item) for item in response.json().get("results", [])]

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

    def _map_region(self, item: dict[str, Any]) -> NetBoxRegion:
        return NetBoxRegion(
            id=int(item["id"]),
            name=item.get("name") or item.get("slug") or str(item["id"]),
            slug=item.get("slug"),
            description=item.get("description"),
        )

    def _map_site(self, item: dict[str, Any]) -> NetBoxSite:
        return NetBoxSite(
            id=int(item["id"]),
            name=item.get("name") or item.get("slug") or str(item["id"]),
            slug=item.get("slug"),
            region=self._nested_name(item.get("region")),
            status=self._display(item.get("status")),
            facility=item.get("facility"),
            physical_address=item.get("physical_address"),
        )

    def _map_device(self, item: dict[str, Any]) -> NetBoxDevice:
        device_type = item.get("device_type") or {}
        manufacturer = device_type.get("manufacturer") if isinstance(device_type, dict) else None
        return NetBoxDevice(
            id=int(item["id"]),
            name=item.get("name") or str(item["id"]),
            display=item.get("display"),
            site=self._nested_name(item.get("site")),
            region=self._nested_name((item.get("site") or {}).get("region")),
            role=self._nested_name(item.get("role") or item.get("device_role")),
            device_type=self._nested_name(device_type),
            manufacturer=self._nested_name(manufacturer),
            status=self._display(item.get("status")),
            primary_ip=self._nested_display(item.get("primary_ip") or item.get("primary_ip4")),
        )

    def _map_interface(self, item: dict[str, Any]) -> NetBoxInterface:
        device = item.get("device") or {}
        return NetBoxInterface(
            id=int(item["id"]),
            name=item.get("name") or str(item["id"]),
            device_id=device.get("id") if isinstance(device, dict) else None,
            device=self._nested_name(device),
            type=self._display(item.get("type")),
            enabled=item.get("enabled"),
            mac_address=item.get("mac_address"),
            description=item.get("description"),
            mode=self._display(item.get("mode")),
            mtu=item.get("mtu"),
            speed=item.get("speed"),
            duplex=self._display(item.get("duplex")),
            untagged_vlan=self._nested_name(item.get("untagged_vlan")),
        )

    def _map_device_detail(
        self, device: dict[str, Any], interfaces: list[NetBoxInterface], cache_key: str
    ) -> NetBoxDeviceDetail:
        basic = self._map_device(device)
        return NetBoxDeviceDetail(
            id=basic.id,
            name=basic.name or str(basic.id),
            site=basic.site,
            region=basic.region,
            location=self._nested_name(device.get("location")),
            role=basic.role,
            device_type=basic.device_type,
            manufacturer=basic.manufacturer,
            platform=self._nested_name(device.get("platform")),
            status=basic.status,
            serial=device.get("serial"),
            asset_tag=device.get("asset_tag"),
            primary_ip=basic.primary_ip,
            comments=device.get("comments"),
            interfaces=interfaces,
            cache={
                "hit": False,
                "key": cache_key,
                "stored_at": datetime.now(UTC).isoformat(),
                "ttl_seconds": self.settings.netbox_device_cache_ttl_seconds,
            },
        )

    async def _cache_get(self, key: str) -> dict[str, Any] | None:
        try:
            return await self.cache.get_json(key)
        except Exception:
            return None

    async def _cache_set(self, key: str, value: dict[str, Any]) -> None:
        try:
            await self.cache.set_json(key, value, self.settings.netbox_device_cache_ttl_seconds)
        except Exception:
            return None

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

    @staticmethod
    def _nested_display(value: Any) -> str | None:
        if not isinstance(value, dict):
            return None
        return value.get("display") or value.get("address") or value.get("name")
