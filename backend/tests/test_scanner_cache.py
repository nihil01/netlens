from datetime import UTC, datetime

from app.core.config import Settings
from app.integrations.fmc.service import (
    CACHE_KEY_FULL,
    CACHE_KEY_RESET_STATUS,
    FMC_CACHE_KEYS,
    FmcMonitoringService,
)
from app.integrations.netbox.service import NetBoxService
from app.ip_intelligence.schemas import NetBoxDevice, NetBoxInventory
from app.scanner import service as scanner_service_module
from app.scanner.scheduler import ScannerScheduler
from app.scanner.service import ScannerService
from app.scanner.store import SCANNER_PROFILES_CACHE_KEY, ScannerProfileStore


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    async def get_json(self, key: str) -> object | None:
        return self.values.get(key)

    async def set_json(
        self,
        key: str,
        value: object,
        ttl_seconds: int | None = None,
    ) -> None:
        self.values[key] = value

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def delete_prefix(self, prefix: str) -> int:
        keys = [key for key in self.values if key.startswith(prefix)]
        for key in keys:
            del self.values[key]
        return len(keys)


async def test_scanner_profile_store_keeps_latest_snapshot_without_expiry() -> None:
    cache = MemoryCache()
    store = ScannerProfileStore(cache=cache)  # type: ignore[arg-type]
    now = datetime.now(UTC)

    await store.save(
        [{"ip": "10.0.0.10", "ports": [22, 443]}],
        trigger="schedule",
        started_at=now,
        finished_at=now,
    )

    latest = await store.get_latest()
    assert latest["hosts_total"] == 1
    assert latest["profiles"][0]["ip"] == "10.0.0.10"
    assert SCANNER_PROFILES_CACHE_KEY in cache.values


async def test_scanner_service_publishes_only_completed_pipeline(monkeypatch) -> None:
    class FakeEngine:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class SuccessfulOrchestrator:
        def __init__(self, engine) -> None:
            self.engine = engine

        async def run_pipeline(self):
            return [{"ip": "10.0.0.11", "ports": [80]}]

    cache = MemoryCache()
    store = ScannerProfileStore(cache=cache)  # type: ignore[arg-type]
    service = ScannerService(
        Settings(scanner_dataset_path="app/scanner/net_dataset.json"),
        profile_store=store,
    )
    monkeypatch.setattr(scanner_service_module, "AdvancedProfilingEngine", FakeEngine)
    monkeypatch.setattr(scanner_service_module, "PipelineOrchestrator", SuccessfulOrchestrator)

    result = await service.run_scheduled_scan()

    assert result["status"] == "completed"
    cached_before_failure = cache.values[SCANNER_PROFILES_CACHE_KEY]

    class FailingOrchestrator(SuccessfulOrchestrator):
        async def run_pipeline(self):
            raise RuntimeError("discovery unavailable")

    monkeypatch.setattr(scanner_service_module, "PipelineOrchestrator", FailingOrchestrator)
    failed = await service.run_scheduled_scan()

    assert failed["status"] == "failed"
    assert cache.values[SCANNER_PROFILES_CACHE_KEY] == cached_before_failure


async def test_inventory_refresh_bypasses_cached_value() -> None:
    cache = MemoryCache()
    cache.values["netbox:inventory"] = {
        "devices": [{"id": 1, "name": "old"}],
        "regions": [],
        "sites": [],
        "interfaces": [],
    }
    service = NetBoxService(
        Settings(netbox_url="https://netbox.example.com", netbox_token="token"),
        cache=cache,  # type: ignore[arg-type]
    )
    service._load_inventory = lambda: NetBoxInventory(devices=[NetBoxDevice(id=2, name="fresh")])  # type: ignore[method-assign]

    inventory = await service.refresh_inventory()

    assert inventory.devices[0].name == "fresh"
    cached = cache.values["netbox:inventory"]
    assert isinstance(cached, dict)
    assert cached["devices"][0]["name"] == "fresh"


async def test_netbox_clear_cache_removes_inventory_and_device_entries_only() -> None:
    cache = MemoryCache()
    cache.values.update(
        {
            "netbox:inventory": {"devices": []},
            "netbox:device:42": {"id": 42},
            "scanner:profiles:latest": {"hosts_total": 1},
        }
    )
    service = NetBoxService(Settings(), cache=cache)  # type: ignore[arg-type]

    deleted = await service.clear_cache()

    assert deleted == 2
    assert cache.values == {"scanner:profiles:latest": {"hosts_total": 1}}


async def test_fmc_clear_monitoring_cache_preserves_unrelated_data() -> None:
    cache = MemoryCache()
    for key in FMC_CACHE_KEYS:
        cache.values[key] = {"old": True}
    cache.values["fmc:audit:unrelated"] = {"preserve": True}
    cache.values[CACHE_KEY_RESET_STATUS] = {"state": "clearing"}
    service = FmcMonitoringService(Settings(), cache=cache)  # type: ignore[arg-type]

    result = await service.clear_monitoring_data()

    assert result["cache_keys_deleted"] == len(FMC_CACHE_KEYS)
    assert result["database_rows_deleted"] == {}
    assert result["audit_preserved"] is True
    assert cache.values == {
        "fmc:audit:unrelated": {"preserve": True},
        CACHE_KEY_RESET_STATUS: {"state": "clearing"},
    }


async def test_fmc_reset_marker_hides_stale_discovered_devices() -> None:
    cache = MemoryCache()
    cache.values[CACHE_KEY_FULL] = {"total_devices": 72}
    cache.values[CACHE_KEY_RESET_STATUS] = {
        "state": "queued",
        "completed_scopes": [],
    }
    service = FmcMonitoringService(Settings(), cache=cache)  # type: ignore[arg-type]

    dashboard = await service.get_dashboard()

    assert dashboard.total_devices == 0
    assert dashboard.devices == []
    assert dashboard.reset_status["state"] == "queued"


def test_vpn_fallback_summarizes_statuses_by_topology() -> None:
    summaries = FmcMonitoringService._summarize_vpn_tunnels(
        [
            {"state": "TUNNEL_UP", "vpnTopology": {"id": "one", "name": "Branch"}},
            {"state": "TUNNEL_DOWN", "vpnTopology": {"id": "one", "name": "Branch"}},
            {"state": "UNKNOWN", "vpnTopology": {"id": "two", "name": "DC"}},
        ]
    )

    assert summaries == [
        {
            "group": {"id": "one", "name": "Branch", "type": "FTDS2SVPNTopology"},
            "tunnelCount": 2,
            "tunnelUpCount": 1,
            "tunnelDownCount": 1,
            "tunnelUnknownCount": 0,
            "type": "TunnelSummary",
        },
        {
            "group": {"id": "two", "name": "DC", "type": "FTDS2SVPNTopology"},
            "tunnelCount": 1,
            "tunnelUpCount": 0,
            "tunnelDownCount": 0,
            "tunnelUnknownCount": 1,
            "type": "TunnelSummary",
        },
    ]


async def test_scheduler_fmc_reset_refetches_scopes_in_safe_order() -> None:
    class FakeFmcClient:
        configured = True

    class FakeCollector:
        client = FakeFmcClient()

    class FakeFmcService:
        collector = FakeCollector()

        def __init__(self) -> None:
            self.calls: list[str] = []

        async def clear_monitoring_data(self):
            self.calls.append("clear")
            return {"cache_keys_deleted": 4, "database_rows_deleted": {}}

        async def set_reset_status(self, state, **kwargs):
            return {"state": state, **kwargs}

        async def refresh_discovery(self):
            self.calls.append("discovery")

        async def refresh_device_health(self):
            self.calls.append("health")

        async def refresh_interfaces(self):
            self.calls.append("interfaces")

        async def refresh_ha(self):
            self.calls.append("ha")

        async def refresh_alerts(self):
            self.calls.append("alerts")

        async def refresh_policy_analysis(self):
            self.calls.append("policy")

        async def refresh_vpn_status(self):
            self.calls.append("vpn")

    service = FakeFmcService()
    scheduler = ScannerScheduler(
        Settings(scanner_schedule_enabled=False, inventory_refresh_enabled=False),
        fmc_factory=lambda: service,  # type: ignore[arg-type]
    )

    accepted = await scheduler.trigger_fmc_reset()
    duplicate = await scheduler.trigger_fmc_reset()
    assert scheduler._fmc_reset_task is not None
    await scheduler._fmc_reset_task

    assert accepted["status"] == "accepted"
    assert duplicate["status"] == "already_running"
    assert service.calls == [
        "clear",
        "discovery",
        "health",
        "interfaces",
        "ha",
        "alerts",
        "policy",
        "vpn",
    ]


async def test_scheduler_reuses_services_and_refreshes_inventory() -> None:
    class FakeScanner:
        calls = 0

        def is_running(self) -> bool:
            return False

        async def run_scheduled_scan(self, trigger: str = "schedule"):
            self.calls += 1
            return {"status": "completed", "hosts_total": 3}

    class FakeInventory:
        calls = 0

        async def refresh_inventory(self):
            self.calls += 1
            return NetBoxInventory(devices=[NetBoxDevice(id=3, name="cached")])

    scanner = FakeScanner()
    inventory = FakeInventory()
    scheduler = ScannerScheduler(
        Settings(scanner_schedule_enabled=False, inventory_refresh_enabled=False),
        scanner_factory=lambda: scanner,  # type: ignore[arg-type]
        inventory_factory=lambda: inventory,  # type: ignore[arg-type]
    )

    await scheduler._run_job()
    await scheduler._run_job()
    await scheduler._run_inventory_job()

    assert scanner.calls == 2
    assert inventory.calls == 1
    assert [item["job"] for item in scheduler.get_history()] == [
        "scanner",
        "scanner",
        "inventory-refresh",
    ]
