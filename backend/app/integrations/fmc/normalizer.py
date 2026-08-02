"""Pure FMC response normalizers.

This module performs no HTTP or persistence and deliberately preserves missing values.
"""

from __future__ import annotations

from typing import Any

from app.integrations.fmc.errors import FmcErrorCategory, FmcRequestError
from app.integrations.fmc.schemas import HardwareFan, MetricStatus

_BLOCK_CAPABILITIES = {
    "cpuHealthMetrics": "aggregateCpu",
    "memoryHealthMetrics": "aggregateMemory",
    "diskHealthMetrics": "aggregateDisk",
    "interfaceHealthMetricsList": "aggregateInterface",
    "chassisStatsHealthMetrics": "aggregateChassis",
}


def select_device_metric(response: dict[str, Any], device_id: str) -> dict[str, Any] | None:
    """Return the metric item for exactly ``device_id`` or reject a mismatched response."""
    items = response.get("items", [])
    if not isinstance(items, list):
        raise FmcRequestError(
            FmcErrorCategory.INVALID_RESPONSE,
            "Aggregate metrics items is not an array",
            path="aggregatemetrics",
        )
    if not items:
        return None
    matching = [item for item in items if isinstance(item, dict) and item.get("id") == device_id]
    if not matching:
        response_ids = [item.get("id") for item in items if isinstance(item, dict)]
        raise FmcRequestError(
            FmcErrorCategory.INVALID_RESPONSE,
            f"Aggregate metrics UUID mismatch for {device_id}; response IDs={response_ids}",
            path="aggregatemetrics",
        )
    return matching[-1]


def normalize_aggregate(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Normalize all aggregate blocks and return per-category capability observations."""
    capabilities: dict[str, str] = {}
    for block_name, capability_name in _BLOCK_CAPABILITIES.items():
        value = item.get(block_name)
        populated = bool(value) if isinstance(value, (dict, list)) else value is not None
        capabilities[capability_name] = "SUPPORTED" if populated else "AVAILABLE_NO_DATA"

    cpu_raw = _object(item.get("cpuHealthMetrics"))
    memory_raw = _object(item.get("memoryHealthMetrics"))
    disk_raw = _object(item.get("diskHealthMetrics"))
    interface_raw = item.get("interfaceHealthMetricsList")
    if not isinstance(interface_raw, list):
        interface_raw = []
    chassis_raw = _object(item.get("chassisStatsHealthMetrics"))

    cpu = _metric_block(
        cpu_raw,
        {
            "linaPercent": "linaUsageAvg",
            "snortPercent": "snortUsageAvg",
            "systemPercent": "systemUsageAvg",
        },
    )
    memory = _metric_block(
        memory_raw,
        {
            "linaPercent": "linaUsageAvg",
            "snortPercent": "snortUsageAvg",
            "systemPercent": "systemUsageAvg",
        },
    )
    disk = _metric_block(disk_raw, {"totalUsagePercent": "totalDiskUsageAvg"})

    interfaces = [
        _normalize_interface_metric(raw) for raw in interface_raw if isinstance(raw, dict)
    ]
    fans: list[dict[str, Any]] = []
    fan_list = chassis_raw.get("fanRpmAvgList", [])
    if isinstance(fan_list, list):
        for raw in fan_list:
            if not isinstance(raw, dict):
                continue
            rpm = _number(raw.get("rpm"))
            fans.append(
                {
                    **HardwareFan(name=raw.get("name"), rpm=rpm).model_dump(),
                    "metricStatus": _status(raw, "rpm").value,
                }
            )

    return (
        {
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
            "interfaces": interfaces,
            "fans": fans,
            "metricWindow": "5m",
            "source": "health_aggregatemetrics",
            "startTime": item.get("startTime"),
            "endTime": item.get("endTime"),
            "presentMetricBlocks": [block for block in _BLOCK_CAPABILITIES if block in item],
        },
        capabilities,
    )


def normalize_operational(items: Any, source_name: str) -> dict[str, Any] | None:
    if not isinstance(items, list) or not items:
        return None
    latest = next((item for item in reversed(items) if isinstance(item, dict)), None)
    if latest is None:
        return None
    raw_metric = _object(latest.get("healthMonitorMetric"))
    value = _number(raw_metric.get("value"))
    status = _status(raw_metric, "value")
    return {
        "systemPercent": value,
        "linaPercent": None,
        "snortPercent": None,
        "metricStatuses": {
            "systemPercent": status.value,
            "linaPercent": MetricStatus.NO_DATA.value,
            "snortPercent": MetricStatus.NO_DATA.value,
        },
        "source": source_name,
    }


def _metric_block(raw: dict[str, Any], fields: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    statuses: dict[str, str] = {}
    for normalized_name, raw_name in fields.items():
        result[normalized_name] = _number(raw.get(raw_name))
        statuses[normalized_name] = _status(raw, raw_name).value
    result["metricStatuses"] = statuses
    return result


def _normalize_interface_metric(raw: dict[str, Any]) -> dict[str, Any]:
    field_map = {
        "inputBytesAverage": "inputBytesAvg",
        "outputBytesAverage": "outputBytesAvg",
        "inputErrorsAverage": "inputErrorsAvg",
        "outputErrorsAverage": "outputErrorsAvg",
        "dropsAverage": "dropPacketsAvg",
        "l2DecodeDropsAverage": "l2DecodeDropsAvg",
        "bufferOverrunsAverage": "bufferOverrunsAvg",
        "bufferUnderrunsAverage": "bufferUnderrunsAvg",
        "inputPacketSizeAverage": "inputPacketSizeAvg",
        "outputPacketSizeAverage": "outputPacketSizeAvg",
    }
    result: dict[str, Any] = {
        "interface": raw.get("interface"),
        "interfaceId": raw.get("interfaceUUID") or raw.get("interfaceId"),
        "interfaceName": raw.get("interfaceName"),
        "interfaceType": raw.get("interfaceType"),
        "linkStatus": raw.get("currentLinkStatus"),
        "operationalStatus": raw.get("currentOperationalStatus"),
        "duplexMode": raw.get("duplexMode"),
    }
    statuses: dict[str, str] = {}
    for normalized_name, raw_name in field_map.items():
        result[normalized_name] = _number(raw.get(raw_name))
        statuses[normalized_name] = _status(raw, raw_name).value
    result["metricStatuses"] = statuses
    has_runtime = any(
        value is not None
        for key, value in result.items()
        if key
        not in {"metricStatuses", "interfaceId", "interface", "interfaceName", "interfaceType"}
    )
    result["metricStatus"] = MetricStatus.VALUE.value if has_runtime else MetricStatus.NO_DATA.value
    return result


def _status(raw: dict[str, Any], key: str) -> MetricStatus:
    if key not in raw or raw.get(key) is None:
        return MetricStatus.NO_DATA
    value = _number(raw.get(key))
    if value is None:
        return MetricStatus.INVALID_RESPONSE
    return MetricStatus.VALUE_ZERO if value == 0 else MetricStatus.VALUE


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
