from app.core.config import Settings
from app.integrations.netbox.mac_vendor import MacVendorResolver
from app.integrations.netbox.service import NetBoxService


class MemoryJsonCache:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.ttl: dict[str, int] = {}

    async def get_json(self, key: str) -> dict | None:
        return self.values.get(key)

    async def set_json(self, key: str, value: dict, ttl_seconds: int) -> None:
        self.values[key] = value
        self.ttl[key] = ttl_seconds


def test_netbox_inventory_mapping_keeps_lists_lightweight() -> None:
    service = NetBoxService(Settings(netbox_url="https://netbox.example.com", netbox_token="token"))
    service.mac_vendor_resolver = MacVendorResolver.from_prefixes({"00:11:22": "Cisco Systems"})

    region = service._map_region({"id": 1, "name": "Azerbaijan", "slug": "az"})
    site = service._map_site(
        {
            "id": 10,
            "name": "Baku HQ",
            "region": {"name": "Azerbaijan"},
            "status": {"label": "Active"},
        }
    )
    device = service._map_device(
        {
            "id": 100,
            "name": "SW-BAKU-01",
            "site": {"name": "Baku HQ", "region": {"name": "Azerbaijan"}},
            "role": {"name": "switch"},
            "device_type": {"name": "C9300", "manufacturer": {"name": "Cisco"}},
            "status": {"value": "active"},
            "primary_ip4": {"address": "10.1.1.10/32"},
            "serial": "heavy-detail-field-should-not-be-in-list-dto",
        }
    )
    interface = service._map_interface(
        {
            "id": 1000,
            "name": "Gi1/0/1",
            "device": {"id": 100, "name": "SW-BAKU-01"},
            "type": {"label": "1000BASE-T"},
            "enabled": True,
            "mac_address": "0011.2233.4455",
        }
    )

    assert region.name == "Azerbaijan"
    assert site.region == "Azerbaijan"
    assert device.manufacturer == "Cisco"
    assert device.primary_ip == "10.1.1.10/32"
    assert not hasattr(device, "serial")
    assert interface.device_id == 100
    assert interface.mac_address == "00:11:22:33:44:55"
    assert interface.mac_vendor == "Cisco Systems"
    assert interface.mac_oui == "00:11:22"


def test_inventory_exposes_wireshark_oui_cache_metadata() -> None:
    service = NetBoxService(Settings(netbox_url="https://netbox.example.com", netbox_token="token"))
    service.mac_vendor_resolver = MacVendorResolver.from_prefixes({"00:11:22": "Cisco Systems"})
    service.mac_vendor_resolver.dataset.lookup_oid("001122")

    metadata = service._mac_vendor_dataset_status()

    assert metadata["source"] == "wireshark-manuf-json"
    assert metadata["source_url"] == ""
    assert metadata["created_at"] is None
    assert metadata["records"] == 0
    assert metadata["cache"] == "memory"


async def test_device_detail_cache_uses_device_id_key() -> None:
    cache = MemoryJsonCache()
    settings = Settings(
        netbox_url="https://netbox.example.com",
        netbox_token="token",
        netbox_device_cache_ttl_seconds=120,
    )
    service = NetBoxService(settings, cache=cache)
    detail = service._map_device_detail(
        {
            "id": 100,
            "name": "SW-BAKU-01",
            "site": {"name": "Baku HQ"},
            "device_type": {"name": "C9300", "manufacturer": {"name": "Cisco"}},
            "serial": "FOC123",
        },
        interfaces=[],
        cache_key="netbox:device:100",
    )

    await service._cache_set("netbox:device:100", detail.model_dump(mode="json"))
    cached = await service._cache_get("netbox:device:100")

    assert cache.ttl["netbox:device:100"] == 120
    assert cached is not None
    assert cached["id"] == 100
    assert cached["serial"] == "FOC123"
