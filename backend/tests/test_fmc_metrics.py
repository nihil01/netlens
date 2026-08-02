from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.api.routes.monitoring import _map_dashboard
from app.core.config import Settings
from app.integrations.fmc.analytics import summarize_access_policies, summarize_health_series
from app.integrations.fmc.client import AGGREGATE_METRIC_CATEGORIES, FmcClient
from app.integrations.fmc.collector import FmcCollector
from app.integrations.fmc.errors import FmcErrorCategory, FmcRequestError
from app.integrations.fmc.normalizer import normalize_aggregate, select_device_metric
from app.integrations.fmc.schemas import (
    CollectedDevice,
    DeviceIdentity,
    InterfaceRuntime,
    MetricStatus,
    NormalizedInterface,
)
from app.integrations.fmc.service import FmcMonitoringService
from app.monitoring.repository import metric_rows_for_device


def test_aggregate_normalizer_preserves_zero_and_missing() -> None:
    load, capabilities = normalize_aggregate(
        {
            "id": "device-1",
            "cpuHealthMetrics": {
                "linaUsageAvg": 0,
                "systemUsageAvg": 12.5,
            },
            "memoryHealthMetrics": {},
            "diskHealthMetrics": {"totalDiskUsageAvg": None},
            "interfaceHealthMetricsList": [
                {
                    "interface": "Ethernet1/1",
                    "currentLinkStatus": "UP",
                    "inputBytesAvg": 0,
                }
            ],
            "chassisStatsHealthMetrics": {"fanRpmAvgList": [{"name": "fan1", "rpm": 15720}]},
        }
    )

    assert load["cpu"]["linaPercent"] == 0
    assert load["cpu"]["metricStatuses"]["linaPercent"] == "VALUE_ZERO"
    assert load["cpu"]["snortPercent"] is None
    assert load["cpu"]["metricStatuses"]["snortPercent"] == "NO_DATA"
    assert load["disk"]["totalUsagePercent"] is None
    assert load["interfaces"][0]["inputBytesAverage"] == 0
    assert load["interfaces"][0]["metricStatuses"]["inputBytesAverage"] == "VALUE_ZERO"
    assert load["interfaces"][0]["outputBytesAverage"] is None
    assert load["fans"][0]["rpm"] == 15720
    assert capabilities["aggregateCpu"] == "SUPPORTED"
    assert capabilities["aggregateMemory"] == "AVAILABLE_NO_DATA"


def test_aggregate_normalizer_rejects_wrong_device_uuid() -> None:
    with pytest.raises(FmcRequestError) as raised:
        select_device_metric({"items": [{"id": "old-device"}]}, "current-device")

    assert raised.value.category == FmcErrorCategory.INVALID_RESPONSE


@pytest.mark.asyncio
async def test_client_classifies_permission_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            request=request,
            json={"error": {"messages": [{"description": "The user is not authorized"}]}},
        )

    client = FmcClient(
        Settings(
            fmc_url="https://fmc.example.com",
            fmc_username="readonly",
            fmc_password="secret",
            fmc_min_request_interval_seconds=0,
        )
    )
    client._token = "not-logged"
    client._domain_uuid = "domain"
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(FmcRequestError) as raised:
        await client.get("/forbidden")

    assert raised.value.category == FmcErrorCategory.PERMISSION_ERROR
    assert raised.value.status_code == 403
    assert client.raw_responses[-1]["error_category"] == "PERMISSION_ERROR"
    assert "not-logged" not in str(client.raw_responses)
    await client.close()


@pytest.mark.asyncio
async def test_client_retries_temporary_fmc_error() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, request=request, json={"error": {}})
        return httpx.Response(200, request=request, json={"items": []})

    client = FmcClient(
        Settings(
            fmc_url="https://fmc.example.com",
            fmc_username="readonly",
            fmc_password="secret",
            fmc_min_request_interval_seconds=0,
        )
    )
    client._token = "token"
    client._domain_uuid = "domain"
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client._backoff = AsyncMock()  # type: ignore[method-assign]

    assert await client.get("/temporary", retries=2) == {"items": []}
    assert calls == 2
    client._backoff.assert_awaited_once()
    await client.close()


@pytest.mark.asyncio
async def test_clients_share_one_serial_fmc_request_lane() -> None:
    in_flight = 0
    max_in_flight = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, request=request, json={"items": []})

    settings = Settings(
        fmc_url="https://serialized-fmc.example.com",
        fmc_username="readonly",
        fmc_password="secret",
        fmc_min_request_interval_seconds=0,
    )
    first = FmcClient(settings)
    second = FmcClient(settings)
    for client in (first, second):
        client._token = "token"
        client._domain_uuid = "domain"
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    await asyncio.gather(first.get("/first"), second.get("/second"))

    assert max_in_flight == 1
    await first.close()
    await second.close()


@pytest.mark.asyncio
async def test_client_retries_429_and_records_rate_limit() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                request=request,
                headers={"Retry-After": "0"},
                json={"error": {}},
            )
        return httpx.Response(200, request=request, json={"items": []})

    client = FmcClient(
        Settings(
            fmc_url="https://rate-limited-fmc.example.com",
            fmc_username="readonly",
            fmc_password="secret",
            fmc_min_request_interval_seconds=0,
            fmc_rate_limit_cooldown_seconds=0,
        )
    )
    client._token = "token"
    client._domain_uuid = "domain"
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client._backoff = AsyncMock()  # type: ignore[method-assign]

    assert await client.get("/rate-limited", retries=2) == {"items": []}
    assert calls == 2
    assert client.raw_responses[0]["error_category"] == "RATE_LIMIT"
    client._backoff.assert_awaited_once()
    await client.close()


@pytest.mark.asyncio
async def test_client_requests_all_aggregate_metrics_in_one_filter() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request, json={"items": []})

    client = FmcClient(
        Settings(
            fmc_url="https://fmc.example.com",
            fmc_username="readonly",
            fmc_password="secret",
            fmc_min_request_interval_seconds=0,
        )
    )
    client._token = "token"
    client._domain_uuid = "domain"
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    await client.get_aggregate_metrics("device-1", AGGREGATE_METRIC_CATEGORIES)

    assert len(requests) == 1
    assert requests[0].url.path.endswith("/health/aggregatemetrics")
    assert requests[0].url.params["filter"] == (
        "metric:CPU,MEM,INTERFACE,DISK_STATS,CHASSIS_STATS;device_uuid:device-1"
    )
    assert requests[0].url.params["expanded"] == "false"
    await client.close()


class _HaListFailureClient:
    configured = True
    raw_responses: list[dict] = []

    def clear_diagnostics(self) -> None:
        return None

    @property
    def domain_uuid(self) -> str:
        return "e276abec-e0f2-11e3-8169-6d9ed49b625f"

    async def authenticate(self) -> str:
        return "token"

    async def get_ha_pairs(self) -> list[dict]:
        raise FmcRequestError(
            FmcErrorCategory.TEMPORARY_FMC_ERROR,
            "FMC returned HTTP 500",
            path="/devicehapairs/ftddevicehapairs",
            status_code=500,
        )


@pytest.mark.asyncio
async def test_ha_scope_does_not_hide_list_http_500_as_empty_success() -> None:
    collector = FmcCollector(Settings())
    collector.client = _HaListFailureClient()  # type: ignore[assignment]

    with pytest.raises(FmcRequestError) as raised:
        await collector.collect(scope="ha", device_summaries=[])

    assert raised.value.status_code == 500


class _AggregateFakeClient:
    def __init__(self, aggregate_error: FmcRequestError | None = None) -> None:
        self.aggregate_error = aggregate_error
        self.metrics_requested: list[tuple[str, ...]] = []
        self.raw_responses: list[dict] = []

    async def get_aggregate_metrics(self, device_id: str, metrics: tuple[str, ...]) -> dict:
        self.metrics_requested.append(tuple(metrics))
        if self.aggregate_error:
            raise self.aggregate_error
        return {
            "items": [
                {
                    "id": device_id,
                    "cpuHealthMetrics": {"systemUsageAvg": 18.25},
                    "memoryHealthMetrics": {"systemUsageAvg": 0},
                    "diskHealthMetrics": {"totalDiskUsageAvg": 0},
                    "interfaceHealthMetricsList": [
                        {"interface": "Ethernet1/1", "inputBytesAvg": 12}
                    ],
                    "chassisStatsHealthMetrics": {
                        "fanRpmAvgList": [{"name": "fan1", "rpm": 15720}]
                    },
                }
            ]
        }


@pytest.mark.asyncio
async def test_collector_requests_all_aggregate_categories_once() -> None:
    collector = FmcCollector(
        Settings(fmc_url="https://fmc", fmc_username="user", fmc_password="pass")
    )
    fake = _AggregateFakeClient()
    collector.client = fake  # type: ignore[assignment]
    capabilities: dict[str, str] = {}
    errors: list[str] = []
    device = DeviceIdentity(id="device-1", is_connected=True)

    load, status = await collector._collect_aggregate_metrics(
        "device-1", device, capabilities, errors
    )

    assert status == MetricStatus.VALUE
    assert load["cpu"]["systemPercent"] == 18.25
    assert load["disk"]["totalUsagePercent"] == 0
    assert load["disk"]["metricStatuses"]["totalUsagePercent"] == "VALUE_ZERO"
    assert load["memory"]["systemPercent"] == 0
    assert load["memory"]["metricStatuses"]["systemPercent"] == "VALUE_ZERO"
    assert load["interfaces"][0]["inputBytesAverage"] == 12
    assert load["fans"][0]["rpm"] == 15720
    assert all(
        capabilities[name] == "SUPPORTED"
        for name in (
            "aggregateCpu",
            "aggregateMemory",
            "aggregateInterface",
            "aggregateDisk",
            "aggregateChassis",
        )
    )
    assert fake.metrics_requested == [AGGREGATE_METRIC_CATEGORIES]


@pytest.mark.asyncio
async def test_collector_does_not_category_fallback_on_permission_error() -> None:
    collector = FmcCollector(
        Settings(fmc_url="https://fmc", fmc_username="user", fmc_password="pass")
    )
    fake = _AggregateFakeClient(
        FmcRequestError(
            FmcErrorCategory.PERMISSION_ERROR,
            "not authorized",
            path="aggregatemetrics",
            status_code=403,
        )
    )
    collector.client = fake  # type: ignore[assignment]
    capabilities: dict[str, str] = {}

    load, status = await collector._collect_aggregate_metrics(
        "device-1",
        DeviceIdentity(id="device-1", is_connected=True),
        capabilities,
        [],
    )

    assert status == MetricStatus.PERMISSION_ERROR
    assert load == {"status": "PERMISSION_ERROR"}
    assert fake.metrics_requested == [AGGREGATE_METRIC_CATEGORIES]


@pytest.mark.asyncio
async def test_collector_does_not_split_temporary_aggregate_failure_into_more_requests() -> None:
    collector = FmcCollector(
        Settings(fmc_url="https://fmc", fmc_username="user", fmc_password="pass")
    )
    fake = _AggregateFakeClient(
        FmcRequestError(
            FmcErrorCategory.TEMPORARY_FMC_ERROR,
            "aggregate request failed",
            path="aggregatemetrics",
            status_code=500,
        )
    )
    collector.client = fake  # type: ignore[assignment]

    load, status = await collector._collect_aggregate_metrics(
        "device-1",
        DeviceIdentity(id="device-1", is_connected=True),
        {},
        [],
    )

    assert status == MetricStatus.TEMPORARY_ERROR
    assert load == {"status": "TEMPORARY_ERROR"}
    assert fake.metrics_requested == [AGGREGATE_METRIC_CATEGORIES]


def test_interface_merge_refuses_ambiguous_case_insensitive_match() -> None:
    collector = FmcCollector(Settings())
    interfaces = [
        NormalizedInterface(id="one", physical_name="Ethernet1/1"),
        NormalizedInterface(id="two", logical_name="ethernet1/1"),
    ]

    collector._merge_interface_runtime(
        interfaces,
        [{"interface": "ETHERNET1/1", "metricStatus": "VALUE"}],
    )

    assert all(interface.sources == [] for interface in interfaces)


def test_dashboard_mapper_uses_only_aggregate_interface_performance() -> None:
    dashboard = _map_dashboard(
        {
            "devices": [
                {
                    "device": {
                        "id": "device-1",
                        "name": "ftd-1",
                        "host_name": "branch-ftd-1",
                    },
                    "aggregate_status": "PERMISSION_ERROR",
                    "load": {
                        "interfaces": [
                            {
                                "interfaceId": "interface-1",
                                "interfaceName": "Ethernet1/1",
                                "inputBytesAverage": None,
                                "outputBytesAverage": None,
                                "metricStatus": "NO_DATA",
                            }
                        ]
                    },
                    "interfaces": [
                        {
                            "id": "interface-1",
                            "physical_name": "Ethernet1/1",
                            "runtime": {},
                            "metric_status": "NO_DATA",
                        }
                    ],
                }
            ]
        }
    )

    metrics = dashboard["aggregate_metrics"][0]
    assert metrics["device_name"] == "ftd-1"
    assert metrics["metric_status"] == "PERMISSION_ERROR"
    assert metrics["cpu_percent"] is None
    assert metrics["interface_traffic"][0]["input_bytes_avg"] is None
    assert metrics["interface_traffic"][0]["output_bytes_avg"] is None
    assert "rx_bytes" not in metrics["interface_traffic"][0]


class _MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}

    async def get_json(self, key: str) -> dict | None:
        return self.values.get(key)

    async def set_json(self, key: str, value: dict, _ttl: int) -> None:
        self.values[key] = value


@pytest.mark.asyncio
async def test_dashboard_cold_cache_never_calls_fmc() -> None:
    service = FmcMonitoringService(Settings(), cache=_MemoryCache())  # type: ignore[arg-type]
    service.collector.collect = AsyncMock()

    dashboard = await service.get_dashboard()

    service.collector.collect.assert_not_awaited()
    assert {item.source: item.state.value for item in dashboard.source_freshness} == {
        "fmc_discovery": "NEVER_COLLECTED",
        "fmc_device_health": "NEVER_COLLECTED",
        "fmc_interfaces": "NEVER_COLLECTED",
        "fmc_alerts": "NEVER_COLLECTED",
        "fmc_ha": "NEVER_COLLECTED",
        "fmc_policy_analysis": "NEVER_COLLECTED",
        "fmc_vpn": "NEVER_COLLECTED",
    }


def test_source_freshness_marks_old_success_stale() -> None:
    service = FmcMonitoringService(
        Settings(fmc_device_health_stale_seconds=60),
        cache=_MemoryCache(),  # type: ignore[arg-type]
    )
    old = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    dashboard = service._merge(
        {},
        {},
        {
            "fmc_device_health": {
                "source": "fmc_device_health",
                "state": "FRESH",
                "last_success": old,
                "stale_threshold_seconds": 60,
            }
        },
    )

    states = {item.source: item.state.value for item in dashboard.source_freshness}
    assert states["fmc_device_health"] == "STALE"


def test_scoped_alert_merge_preserves_health_and_interfaces() -> None:
    service = FmcMonitoringService(Settings(), cache=_MemoryCache())  # type: ignore[arg-type]
    current = {
        "domain_id": str(uuid4()),
        "devices": [
            {
                "device": {"id": "device-1", "name": "ftd"},
                "load": {"cpu": {"systemPercent": 12}},
                "interfaces": [{"id": "interface-1"}],
                "alerts": [{"id": "old"}],
                "capabilities": {"aggregateAll": "SUPPORTED"},
            }
        ],
    }
    component = {
        "collection_run_id": str(uuid4()),
        "domain_id": current["domain_id"],
        "devices": [
            {
                "device": {"id": "device-1", "name": "ftd"},
                "alerts": [{"id": "new", "status": "RED"}],
                "capabilities": {"healthAlerts": "SUPPORTED"},
            }
        ],
    }

    merged = service._merge_scope(current, component, "alerts")

    assert merged["devices"][0]["load"]["cpu"]["systemPercent"] == 12
    assert merged["devices"][0]["interfaces"] == [{"id": "interface-1"}]
    assert merged["devices"][0]["alerts"] == [{"id": "new", "status": "RED"}]
    assert merged["alerts_red"] == 1


def test_metric_history_rows_preserve_missing_and_zero_status() -> None:
    domain_id = str(uuid4())
    device_id = str(uuid4())
    collected = CollectedDevice(
        domain_id=domain_id,
        device=DeviceIdentity(id=device_id),
        aggregate_status=MetricStatus.PARTIAL,
        load={
            "cpu": {
                "systemPercent": 0,
                "linaPercent": None,
                "metricStatuses": {
                    "systemPercent": "VALUE_ZERO",
                    "linaPercent": "NO_DATA",
                },
            },
            "source": "health_aggregatemetrics",
            "metricWindow": "5m",
        },
        interfaces=[
            NormalizedInterface(
                id="interface-1",
                metric_status=MetricStatus.VALUE,
                runtime=InterfaceRuntime(
                    link_status="DOWN",
                    input_bytes_average=0,
                    output_bytes_average=None,
                    metric_status=MetricStatus.VALUE,
                ),
            )
        ],
    )

    rows = metric_rows_for_device(collected, str(uuid4()), datetime.now(UTC))
    indexed = {(row["metric_name"], row.get("interface_id")): row for row in rows}

    assert indexed[("cpu.system", None)]["metric_value"] == 0
    assert indexed[("cpu.system", None)]["metric_status"] == "VALUE_ZERO"
    assert indexed[("cpu.lina", None)]["metric_value"] is None
    assert indexed[("cpu.lina", None)]["metric_status"] == "NO_DATA"
    assert indexed[("interface.link_status", "interface-1")]["metric_value"] == 0
    assert indexed[("interface.link_status", "interface-1")]["metric_status"] == "VALUE_ZERO"
    assert indexed[("interface.output_bytes_avg", "interface-1")]["metric_value"] is None


def test_metric_history_rows_use_aggregate_interfaces_without_config_fetch() -> None:
    collected = CollectedDevice(
        domain_id=str(uuid4()),
        device=DeviceIdentity(id=str(uuid4()), name="branch-ftd"),
        aggregate_status=MetricStatus.VALUE,
        load={
            "source": "health_aggregatemetrics",
            "metricWindow": "5m",
            "interfaces": [
                {
                    "interfaceId": "aggregate-interface-1",
                    "interfaceName": "Ethernet1/1",
                    "inputBytesAverage": 1024,
                    "outputBytesAverage": 0,
                    "dropsAverage": None,
                    "metricStatus": "VALUE",
                    "metricStatuses": {
                        "inputBytesAverage": "VALUE",
                        "outputBytesAverage": "VALUE_ZERO",
                    },
                }
            ],
        },
    )

    rows = metric_rows_for_device(collected, str(uuid4()), datetime.now(UTC))
    indexed = {(row["metric_name"], row.get("interface_id")): row for row in rows}

    assert indexed[("interface.input_bytes_avg", "aggregate-interface-1")][
        "metric_value"
    ] == 1024
    assert indexed[("interface.output_bytes_avg", "aggregate-interface-1")][
        "metric_status"
    ] == "VALUE_ZERO"


def test_ha_configured_members_are_distinct_from_runtime_roles() -> None:
    collector = FmcCollector(Settings())
    pair = collector._parse_ha_pair(
        {
            "id": "pair-1",
            "healthStatus": "HEALTHY",
            "primary": {"id": "device-primary"},
            "secondary": {"id": "device-secondary"},
            "metadata": {
                "primaryStatus": {"currentStatus": "Standby"},
                "secondaryStatus": {"currentStatus": "Active"},
            },
        }
    )

    assert pair.primary.role == "PRIMARY"
    assert pair.primary.runtime_role == "Standby"
    assert pair.secondary.role == "SECONDARY"
    assert pair.secondary.runtime_role == "Active"
    assert pair.active_member_id == "device-secondary"
    assert pair.standby_member_id == "device-primary"
    assert pair.pair_state == "HEALTHY"


def test_ha_split_brain_signal_is_failed_not_healthy() -> None:
    collector = FmcCollector(Settings())
    pair = collector._parse_ha_pair(
        {
            "id": "pair-1",
            "healthStatus": "HEALTHY",
            "primary": {"id": "device-primary"},
            "secondary": {"id": "device-secondary"},
            "metadata": {
                "primaryStatus": {"currentStatus": "Active"},
                "secondaryStatus": {"currentStatus": "Active"},
            },
        }
    )

    assert pair.active_member_id is None
    assert pair.pair_state == "FAILED"


def test_ha_failed_member_signal_is_failed_without_health_status() -> None:
    collector = FmcCollector(Settings())
    pair = collector._parse_ha_pair(
        {
            "id": "pair-1",
            "primary": {"id": "device-primary"},
            "secondary": {"id": "device-secondary"},
            "metadata": {
                "configStatus": "HEALTHY_CONFIG",
                "primaryStatus": {"currentStatus": "Active"},
                "secondaryStatus": {"currentStatus": "Failed"},
            },
        }
    )

    assert pair.active_member_id == "device-primary"
    assert pair.standby_member_id is None
    assert pair.pair_state == "FAILED"


def test_ha_active_standby_is_healthy_when_fmc_omits_health_status() -> None:
    collector = FmcCollector(Settings())
    pair = collector._parse_ha_pair(
        {
            "id": "pair-1",
            "primary": {"id": "device-primary"},
            "secondary": {"id": "device-secondary"},
            "metadata": {
                "configStatus": "HEALTHY_CONFIG",
                "primaryStatus": {"currentStatus": "Active"},
                "secondaryStatus": {"currentStatus": "Standby"},
            },
        }
    )

    assert pair.pair_state == "HEALTHY"


def test_ha_monitored_interface_parser_normalizes_openapi_fields() -> None:
    parsed = FmcCollector._parse_ha_monitored_interface(
        {
            "id": "interface-1",
            "interfaceLogicalName": "inside",
            "monitorForFailures": "true",
            "ipv4Configuration": {
                "activeIPv4Address": "192.0.2.1",
                "activeIPv4Mask": "25",
                "standbyIPv4Address": "192.0.2.2",
            },
            "ipv6Configuration": {
                "activeIPv6LinkLocalAddress": "fe80::1",
                "standbyIPv6LinkLocalAddress": "fe80::2",
                "ipv6ActiveStandbyPair": [
                    {"activeIPv6": "2001:db8::1", "standbyIPv6": "2001:db8::2"}
                ],
            },
        }
    )

    assert parsed.interface_logical_name == "inside"
    assert parsed.monitor_for_failures is True
    assert parsed.ipv4.active_address == "192.0.2.1"
    assert parsed.ipv4.standby_address == "192.0.2.2"
    assert parsed.ipv6.address_pairs[0].active_address == "2001:db8::1"


@pytest.mark.asyncio
async def test_client_ha_interface_list_and_detail_paths_match_openapi() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/monitoredinterfaces"):
            return httpx.Response(
                200,
                request=request,
                json={"items": [{"id": "interface-1"}], "paging": {"count": 1}},
            )
        return httpx.Response(200, request=request, json={"id": "interface-1"})

    client = FmcClient(
        Settings(
            fmc_url="https://ha-interface-fmc.example.com",
            fmc_username="readonly",
            fmc_password="secret",
            fmc_min_request_interval_seconds=0,
        )
    )
    client._token = "token"
    client._domain_uuid = "domain"
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    assert await client.get_ha_monitored_interfaces("pair-1") == [{"id": "interface-1"}]
    assert await client.get_ha_monitored_interface("pair-1", "interface-1") == {"id": "interface-1"}
    assert paths == [
        "/api/fmc_config/v1/domain/domain/devicehapairs/ftddevicehapairs/pair-1/monitoredinterfaces",
        "/api/fmc_config/v1/domain/domain/devicehapairs/ftddevicehapairs/pair-1/monitoredinterfaces/interface-1",
    ]
    await client.close()


def test_health_series_summary_parses_fmc_prometheus_matrix() -> None:
    summary = summarize_health_series(
        {
            "items": [
                {
                    "deviceUUID": "device-1",
                    "response": (
                        '{"data":{"result":[{"values":[[100,"0"],[160,"10.5"],[220,"20"]]}]}}'
                    ),
                }
            ]
        },
        expected_device_id="device-1",
    )

    assert summary == {
        "average": 10.17,
        "maximum": 20.0,
        "latest": 20.0,
        "sample_count": 3,
        "start_time": 100.0,
        "end_time": 220.0,
    }


def test_policy_analysis_counts_review_findings() -> None:
    summary = summarize_access_policies(
        [{"id": "policy-1", "name": "ACP"}],
        {
            "policy-1": [
                {
                    "id": "rule-1",
                    "enabled": True,
                    "action": "ALLOW",
                    "sourceNetworks": {},
                    "destinationNetworks": {},
                    "destinationPorts": {},
                    "logBegin": False,
                    "logEnd": False,
                },
                {"id": "rule-2", "enabled": False, "action": "BLOCK"},
            ]
        },
    )

    assert summary["total_policies"] == 1
    assert summary["total_rules"] == 2
    assert summary["allow_rules_without_ips_policy"] == 1
    assert summary["rules_without_logging"] == 1
    assert summary["rules_with_any_source"] == 1
