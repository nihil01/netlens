from app.core.config import Settings
from app.integrations.netbox.mac_vendor import MacVendorResolver
from app.integrations.netbox.service import NetBoxService
from app.ip_intelligence.schemas import NetBoxMacAddress


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


def test_interface_mapping_filters_own_mac_from_learned_table() -> None:
    service = NetBoxService(Settings(netbox_url="https://netbox.example.com", netbox_token="token"))
    learned = NetBoxMacAddress(mac_address="AA:BB:CC:00:00:01", mac_vendor="Endpoint Vendor")
    own = NetBoxMacAddress(mac_address="00:11:22:33:44:55", mac_vendor="Cisco")

    interface = service._map_interface(
        {
            "id": 1000,
            "name": "GigabitEthernet1/0/1",
            "device": {"id": 100, "name": "SW-BAKU-01"},
            "mac_address": "0011.2233.4455",
        },
        {1000: [own, learned]},
    )

    assert [item.mac_address for item in interface.learned_mac_addresses] == ["AA:BB:CC:00:00:01"]


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


class FakeEndpoint:
    def __init__(self, items=None, get_items=None, fail_all=False) -> None:
        self.items = items or []
        self.get_items = get_items or {}
        self.fail_all = fail_all
        self.all_calls = 0
        self.filter_calls: list[dict] = []

    def all(self):
        self.all_calls += 1
        if self.fail_all:
            raise AssertionError("mac_addresses.all must not be used for device detail")
        return self.items

    def filter(self, **kwargs):
        self.filter_calls.append(kwargs)
        assigned_ids = kwargs.get("assigned_object_id")
        if assigned_ids is None:
            return self.items
        if isinstance(assigned_ids, list):
            allowed = set(assigned_ids)
        else:
            allowed = {assigned_ids}
        return [item for item in self.items if item.get("assigned_object_id") in allowed]

    def get(self, item_id):
        return self.get_items.get(item_id)


class FakeDcim:
    def __init__(self, *, devices, interfaces, mac_addresses) -> None:
        self.devices = devices
        self.interfaces = interfaces
        self.mac_addresses = mac_addresses


class FakeNetBox:
    def __init__(self, dcim) -> None:
        self.dcim = dcim


def test_device_detail_loads_macs_only_for_selected_device_interfaces() -> None:
    service = NetBoxService(Settings(netbox_url="https://netbox.example.com", netbox_token="token"))
    device = {"id": 100, "name": "SW-BAKU-01", "site": {"name": "Baku HQ"}}
    interfaces = [
        {"id": 1000, "name": "Gi1/0/1", "device": {"id": 100, "name": "SW-BAKU-01"}},
        {"id": 1001, "name": "Gi1/0/2", "device": {"id": 100, "name": "SW-BAKU-01"}},
    ]
    macs = [
        {"assigned_object_id": 1000, "mac_address": "AA:BB:CC:00:00:01"},
        {"assigned_object_id": 9999, "mac_address": "AA:BB:CC:00:00:FF"},
    ]
    mac_endpoint = FakeEndpoint(macs, fail_all=True)
    netbox = FakeNetBox(
        FakeDcim(
            devices=FakeEndpoint(get_items={100: device}),
            interfaces=FakeEndpoint(interfaces),
            mac_addresses=mac_endpoint,
        )
    )
    service.netbox = netbox  # type: ignore[assignment]

    detail = service._load_device_detail(100, "netbox:device:100")

    assert mac_endpoint.all_calls == 0
    assert mac_endpoint.filter_calls == [
        {"assigned_object_type": "dcim.interface", "assigned_object_id": [1000, 1001]}
    ]
    assert [item.name for item in detail.interfaces] == ["Gi1/0/1", "Gi1/0/2"]
    assert [item.mac_address for item in detail.interfaces[0].learned_mac_addresses] == [
        "AA:BB:CC:00:00:01"
    ]
    assert detail.interfaces[1].learned_mac_addresses == []
