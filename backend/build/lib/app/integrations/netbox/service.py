import asyncio
import ipaddress
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import pynetbox
from pynetbox import Api

from app.cache.redis_cache import JsonRedisCache
from app.core.config import Settings, get_settings
from app.integrations.netbox.mac_vendor import MacVendorResolver
from app.ip_intelligence.schemas import (
    IntegrationStatus,
    NetBoxContext,
    NetBoxDevice,
    NetBoxDeviceDetail,
    NetBoxInterface,
    NetBoxInventory,
    NetBoxMacAddress,
    NetBoxRegion,
    NetBoxRegionsResponse,
    NetBoxSite,
)
from app.scanner.arp_cache import lookup_arp_mac


class NetBoxService:
    def __init__(
        self, settings: Settings | None = None, cache: JsonRedisCache | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or JsonRedisCache()
        self.netbox: pynetbox.core.api.Api | None = None
        self.mac_vendor_resolver = MacVendorResolver()

    @classmethod
    def from_settings(cls) -> "NetBoxService":
        return cls(get_settings())

    @classmethod
    def build_netbox_client(cls) -> Api:
        settings = get_settings()

        pb = pynetbox.api(
            str(settings.netbox_url).rstrip("/"),
            token=settings.netbox_token,
        )

        pb.http_session.verify = False

        return pb

    def _is_configured(self) -> bool:
        return bool(self.settings.netbox_url and self.settings.netbox_token)

    def _connect(self) -> pynetbox.core.api.Api:
        if self.netbox is None:
            self.netbox = pynetbox.api(
                str(self.settings.netbox_url).rstrip("/"),
                token=self.settings.netbox_token,
            )
            self.netbox.http_session.verify = self.settings.netbox_verify_ssl
            self.netbox.http_session.timeout = self.settings.netbox_timeout_seconds
        return self.netbox

    async def fetch_all(self) -> NetBoxRegionsResponse:
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
                device.model_copy(
                    update={
                        "interfaces": interfaces_by_device[device.id],
                    }
                )
            )

        for site in inventory.sites:
            if not site.region:
                continue

            sites_by_region[site.region].append(
                site.model_copy(
                    update={
                        "devices": devices_by_site[site.name],
                    }
                )
            )

        regions = [
            region.model_copy(
                update={
                    "sites": sites_by_region[region.name],
                }
            )
            for region in inventory.regions
        ]

        return NetBoxRegionsResponse(regions=regions)

    async def get_inventory(self) -> NetBoxInventory:
        cache_key = "netbox:inventory"

        cached = await self._cache_get(cache_key)
        if cached:
            return NetBoxInventory.model_validate(cached)

        if not self._is_configured():
            return NetBoxInventory(
                status=IntegrationStatus(
                    status="not_configured",
                    message="NETBOX_URL and NETBOX_TOKEN are required",
                )
            )

        try:
            inventory = await asyncio.to_thread(self._load_inventory)

            await self._cache_set(
                cache_key,
                inventory.model_dump(mode="json"),
            )

            return inventory

        except Exception as exc:
            return NetBoxInventory(
                status=IntegrationStatus(
                    status="error",
                    message=f"NetBox mapping error: {exc}",
                )
            )

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
            return await asyncio.to_thread(self._lookup_ip_sync, ip)
        except Exception as exc:  # defensive boundary: API shape differs by NetBox version
            return NetBoxContext(
                known=False,
                status=IntegrationStatus(status="error", message=f"NetBox mapping error: {exc}"),
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

        detail = await asyncio.to_thread(self._load_device_detail, device_id, cache_key)
        await self._cache_set(cache_key, detail.model_dump(mode="json"))
        return detail

    def _load_inventory(self) -> NetBoxInventory:
        netbox = self._connect()
        regions = list(netbox.dcim.regions.all())
        sites = list(netbox.dcim.sites.all())
        devices = list(netbox.dcim.devices.all())
        interfaces = list(netbox.dcim.interfaces.all())
        learned_macs_by_interface = self._load_mac_addresses_by_interface(netbox)

        return NetBoxInventory(
            regions=[self._map_region(item) for item in regions],
            sites=[self._map_site(item) for item in sites],
            devices=[self._map_device(item) for item in devices],
            interfaces=[
                self._map_interface(item, learned_macs_by_interface) for item in interfaces
            ],
            oui_dataset=self._mac_vendor_dataset_status(),
        )

    def _mac_vendor_dataset_status(self) -> dict[str, Any]:
        return self.mac_vendor_resolver.dataset.status()

    def _load_device_detail(self, device_id: int, cache_key: str) -> NetBoxDeviceDetail:
        netbox = self._connect()
        device = netbox.dcim.devices.get(device_id)
        if device is None:
            raise NetBoxDeviceNotFound(device_id)

        raw_interfaces = list(netbox.dcim.interfaces.filter(device_id=device_id))
        interface_ids = [
            int(self._field(item, "id")) for item in raw_interfaces if self._field(item, "id")
        ]
        learned_macs_by_interface = self._load_mac_addresses_by_interface(
            netbox,
            interface_ids=interface_ids,
        )
        interfaces = [
            self._map_interface(item, learned_macs_by_interface) for item in raw_interfaces
        ]
        return self._map_device_detail(device, interfaces, cache_key)

    def _lookup_ip_sync(self, ip: str) -> NetBoxContext:
        netbox = self._connect()
        ip_object = self._find_ip_address(netbox, ip)
        if not ip_object:
            return NetBoxContext(known=False, arp_mac_address=lookup_arp_mac(ip))

        assigned = self._field(ip_object, "assigned_object")
        device = self._extract_device(assigned)
        interfaces = []
        if device and self._field(device, "id"):
            device_id = int(self._field(device, "id"))
            raw_interfaces = list(netbox.dcim.interfaces.filter(device_id=device_id))
            interface_ids = [
                int(self._field(item, "id")) for item in raw_interfaces if self._field(item, "id")
            ]
            learned_macs_by_interface = self._load_mac_addresses_by_interface(
                netbox,
                interface_ids=interface_ids,
            )
            interfaces = [
                self._map_interface(item, learned_macs_by_interface).model_dump()
                for item in raw_interfaces
            ]

        return self._map_context(ip_object, device, interfaces)

    def _load_mac_addresses_by_interface(
        self,
        netbox: pynetbox.core.api.Api,
        device_id: int | None = None,
        interface_ids: list[int] | None = None,
    ) -> dict[int, list[NetBoxMacAddress]]:
        grouped: dict[int, list[NetBoxMacAddress]] = defaultdict(list)

        try:
            mac_addresses = list(
                self._iter_mac_addresses(netbox, device_id=device_id, interface_ids=interface_ids)
            )
        except Exception:
            return grouped

        allowed_interface_ids = set(interface_ids or [])
        for item in mac_addresses:
            assigned = self._field(item, "assigned_object")
            interface_id = self._field(assigned, "id") or self._field(item, "assigned_object_id")
            assigned_device = self._field(assigned, "device") if assigned else None

            if not interface_id:
                continue
            interface_id = int(interface_id)
            if allowed_interface_ids and interface_id not in allowed_interface_ids:
                continue
            if device_id is not None and self._field(assigned_device, "id") != device_id:
                continue

            mac = self._field(item, "mac_address") or self._field(item, "address")
            if not mac:
                continue

            mac_info = self.mac_vendor_resolver.lookup(str(mac))
            description = self._field(item, "description")
            grouped[interface_id].append(
                NetBoxMacAddress(
                    mac_address=mac_info.mac_address,
                    mac_vendor=mac_info.vendor,
                    mac_oui=mac_info.oui,
                    mac_vendor_source=mac_info.source,
                    description=description,
                    vlan=self._description_token(description, "vlan"),
                    type=self._description_token(description, "type"),
                )
            )

        return grouped

    def _iter_mac_addresses(
        self,
        netbox: pynetbox.core.api.Api,
        *,
        device_id: int | None = None,
        interface_ids: list[int] | None = None,
    ) -> list[Any]:
        if interface_ids is not None:
            if not interface_ids:
                return []
            return self._filter_mac_addresses_for_interfaces(netbox, interface_ids)

        mac_addresses = list(netbox.dcim.mac_addresses.all())
        if device_id is None:
            return mac_addresses
        return mac_addresses

    def _filter_mac_addresses_for_interfaces(
        self,
        netbox: pynetbox.core.api.Api,
        interface_ids: list[int],
    ) -> list[Any]:
        unique_ids = sorted(set(interface_ids))
        try:
            return list(
                netbox.dcim.mac_addresses.filter(
                    assigned_object_type="dcim.interface",
                    assigned_object_id=unique_ids,
                )
            )
        except Exception:
            results: list[Any] = []
            for interface_id in unique_ids:
                results.extend(
                    list(
                        netbox.dcim.mac_addresses.filter(
                            assigned_object_type="dcim.interface",
                            assigned_object_id=interface_id,
                        )
                    )
                )
            return results

    def _find_ip_address(self, netbox: pynetbox.core.api.Api, ip: str) -> Any | None:
        for item in netbox.ipam.ip_addresses.filter(q=ip):
            if self._address_without_prefix(self._field(item, "address")) == ip:
                return item

        address = f"{ip}/32" if ipaddress.ip_address(ip).version == 4 else f"{ip}/128"
        for item in netbox.ipam.ip_addresses.filter(address=address):
            return item
        return None

    def _map_context(
        self,
        ip_object: Any,
        device: Any | None,
        interfaces: list[dict[str, Any]],
    ) -> NetBoxContext:
        ip = self._address_without_prefix(self._field(ip_object, "address")) or ""

        if not device:
            return NetBoxContext(
                known=True,
                arp_mac_address=lookup_arp_mac(ip),
                interfaces=interfaces,
            )

        site = self._field(device, "site")
        region = self._field(site, "region") if site else None
        location = self._field(device, "location")
        role = self._field(device, "role") or self._field(device, "device_role")

        return NetBoxContext(
            known=True,
            arp_mac_address=lookup_arp_mac(ip),
            device=self._field(device, "name"),
            site=self._name(site),
            region=self._name(region),
            city=self._name(location) or self._field(site, "physical_address") or self._name(site),
            role=self._name(role),
            interfaces=interfaces,
        )

    def _map_region(self, item: Any) -> NetBoxRegion:
        return NetBoxRegion(
            id=int(self._field(item, "id")),
            name=(
                self._field(item, "name")
                or self._field(item, "slug")
                or str(self._field(item, "id"))
            ),
            slug=self._field(item, "slug"),
            description=self._field(item, "description"),
        )

    def _map_site(self, item: Any) -> NetBoxSite:
        return NetBoxSite(
            id=int(self._field(item, "id")),
            name=(
                self._field(item, "name")
                or self._field(item, "slug")
                or str(self._field(item, "id"))
            ),
            slug=self._field(item, "slug"),
            region=self._name(self._field(item, "region")),
            status=self._label(self._field(item, "status")),
            facility=self._field(item, "facility"),
            physical_address=self._field(item, "physical_address"),
        )

    def _map_device(self, item: Any) -> NetBoxDevice:
        device_type = self._field(item, "device_type")
        manufacturer = self._field(device_type, "manufacturer") if device_type else None
        site = self._field(item, "site")
        return NetBoxDevice(
            id=int(self._field(item, "id")),
            name=self._field(item, "name") or str(self._field(item, "id")),
            display=self._field(item, "display"),
            site=self._name(site),
            region=self._name(self._field(site, "region") if site else None),
            role=self._name(self._field(item, "role") or self._field(item, "device_role")),
            device_type=self._device_type_name(device_type),
            manufacturer=self._name(manufacturer),
            status=self._label(self._field(item, "status")),
            primary_ip=self._display(
                self._field(item, "primary_ip") or self._field(item, "primary_ip4")
            ),
        )

    def _map_interface(
        self,
        item: Any,
        learned_macs_by_interface: dict[int, list[NetBoxMacAddress]] | None = None,
    ) -> NetBoxInterface:
        device = self._field(item, "device")
        mac = self._field(item, "mac_address")
        mac_info = self.mac_vendor_resolver.lookup(str(mac)) if mac else None
        interface_id = int(self._field(item, "id"))
        own_mac = mac_info.mac_address if mac_info else mac
        learned_macs = [
            learned
            for learned in (learned_macs_by_interface or {}).get(interface_id, [])
            if learned.mac_address != own_mac
        ]
        return NetBoxInterface(
            id=interface_id,
            name=self._field(item, "name") or str(self._field(item, "id")),
            device_id=self._field(device, "id") if device else None,
            device=self._name(device),
            type=self._label(self._field(item, "type")),
            enabled=self._field(item, "enabled"),
            mac_address=mac_info.mac_address if mac_info else mac,
            mac_vendor=mac_info.vendor if mac_info else None,
            mac_oui=mac_info.oui if mac_info else None,
            mac_vendor_source=mac_info.source if mac_info else "missing",
            description=self._field(item, "description"),
            mode=self._label(self._field(item, "mode")),
            mtu=self._field(item, "mtu"),
            speed=self._field(item, "speed"),
            duplex=self._label(self._field(item, "duplex")),
            untagged_vlan=self._name(self._field(item, "untagged_vlan")),
            learned_mac_addresses=learned_macs,
        )

    def _map_device_detail(
        self, device: Any, interfaces: list[NetBoxInterface], cache_key: str
    ) -> NetBoxDeviceDetail:
        basic = self._map_device(device)
        return NetBoxDeviceDetail(
            id=basic.id,
            name=basic.name or str(basic.id),
            site=basic.site,
            region=basic.region,
            location=self._name(self._field(device, "location")),
            role=basic.role,
            device_type=basic.device_type,
            manufacturer=basic.manufacturer,
            platform=self._name(self._field(device, "platform")),
            status=basic.status,
            serial=self._field(device, "serial"),
            asset_tag=self._field(device, "asset_tag"),
            primary_ip=basic.primary_ip,
            comments=self._field(device, "comments"),
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

    @classmethod
    def _extract_device(cls, assigned: Any) -> Any | None:
        if not assigned:
            return None
        device = cls._field(assigned, "device")
        if device:
            return device
        vm = cls._field(assigned, "virtual_machine")
        if vm:
            if isinstance(vm, dict):
                return {**vm, "role": {"name": "virtual-machine"}}
            return vm
        return None

    @staticmethod
    def _address_without_prefix(address: str | None) -> str | None:
        return address.split("/", 1)[0] if address else None

    @staticmethod
    def _field(value: Any, name: str) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return value.get(name)
        return getattr(value, name, None)

    @classmethod
    def _label(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return value.get("label") or value.get("value") or value.get("name")
        return (
            getattr(value, "label", None)
            or getattr(value, "value", None)
            or getattr(value, "name", None)
            or str(value)
        )

    @classmethod
    def _name(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return value.get("name") or value.get("display")
        return getattr(value, "name", None) or getattr(value, "display", None) or str(value)

    @classmethod
    def _display(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return value.get("display") or value.get("address") or value.get("name")
        return (
            getattr(value, "display", None) or getattr(value, "address", None) or cls._name(value)
        )

    @staticmethod
    def _description_token(description: str | None, key: str) -> str | None:
        if not description:
            return None
        marker = f"{key}="
        for part in str(description).split("|"):
            value = part.strip()
            if value.startswith(marker):
                return value[len(marker) :].strip() or None
        return None

    @classmethod
    def _device_type_name(cls, device_type: Any) -> str | None:
        if device_type is None:
            return None
        if isinstance(device_type, dict):
            return device_type.get("model") or device_type.get("display") or device_type.get("name")
        return (
            getattr(device_type, "model", None)
            or getattr(device_type, "display", None)
            or getattr(device_type, "name", None)
            or str(device_type)
        )


class NetBoxDeviceNotFound(Exception):
    def __init__(self, device_id: int) -> None:
        super().__init__(f"NetBox device {device_id} not found")
        self.device_id = device_id
