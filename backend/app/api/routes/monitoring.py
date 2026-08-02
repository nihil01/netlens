"""FMC Monitoring API routes — single dashboard endpoint."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db import get_db_session
from app.integrations.fmc.service import FmcMonitoringService
from app.monitoring.service import MonitoringHistoryService

router = APIRouter()
_sse_clients = 0


def _get_fmc_service() -> FmcMonitoringService:
    return FmcMonitoringService.from_settings()


def _first_present(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _map_dashboard(raw: dict) -> dict[str, Any]:
    """Transform backend MonitoringDashboard → frontend MonitoringDashboard format."""
    devices = raw.get("devices", [])

    # Build flat FmcDevice[] from CollectedDevice[]
    fmc_devices = []
    for d in devices:
        dev = d.get("device", {})
        load = d.get("load", {})
        fmc_devices.append(
            {
                "id": dev.get("id"),
                "name": dev.get("name"),
                "host_name": dev.get("host_name"),
                "model": dev.get("model"),
                "model_number": dev.get("model_number"),
                "model_id": dev.get("model_id"),
                "sw_version": dev.get("sw_version"),
                "snort_engine": dev.get("snort_engine"),
                "is_connected": dev.get("is_connected"),
                "health_status": dev.get("health_status"),
                "health_message": dev.get("health_message"),
                "deployment_status": dev.get("deployment_status"),
                "ftd_mode": dev.get("ftd_mode"),
                "serial_number": dev.get("serial_number"),
                "access_policy": dev.get("access_policy"),
                "license_caps": dev.get("license_caps", []),
                "performance_tier": dev.get("performance_tier"),
                "snort_version": dev.get("snort_version"),
                "sru_version": dev.get("sru_version"),
                "vdb_version": dev.get("vdb_version"),
                "inventory": {
                    "cpu_type": None,
                    "cpu_cores": None,
                    "memory_mb": None,
                    "storage_gb": None,
                },
                # Attach load so DeviceHealthCard can use it
                "_load": load,
                "_interfaces": d.get("interfaces", []),
                "_capabilities": d.get("capabilities", {}),
            }
        )

    # Build flat aggregate_metrics[] from device load data
    aggregate_metrics = []
    for d in devices:
        load = d.get("load", {})
        dev = d.get("device", {})
        cpu = load.get("cpu", {})
        mem = load.get("memory", {})
        disk = load.get("disk", {})
        ifaces = d.get("interfaces", [])
        aggregate_ifaces = load.get("interfaces", [])
        if not isinstance(aggregate_ifaces, list):
            aggregate_ifaces = []

        aggregate_metrics.append(
            {
                "device_id": dev.get("id"),
                "device_name": dev.get("name") or dev.get("host_name") or dev.get("id"),
                "metric_status": d.get("aggregate_status", "NO_DATA"),
                "cpu_percent": _first_present(
                    cpu.get("systemPercent"), cpu.get("linaPercent"), cpu.get("snortPercent")
                ),
                "cpu_lina_percent": cpu.get("linaPercent"),
                "cpu_snort_percent": cpu.get("snortPercent"),
                "cpu_system_percent": cpu.get("systemPercent"),
                "cpu_metric_statuses": cpu.get("metricStatuses", {}),
                "snort_cpu_average": (load.get("snortHistory") or {}).get("average"),
                "snort_cpu_maximum": (load.get("snortHistory") or {}).get("maximum"),
                "snort_cpu_sample_count": (load.get("snortHistory") or {}).get("sample_count", 0),
                "memory_percent": _first_present(
                    mem.get("systemPercent"), mem.get("linaPercent"), mem.get("snortPercent")
                ),
                "memory_lina_percent": mem.get("linaPercent"),
                "memory_snort_percent": mem.get("snortPercent"),
                "memory_system_percent": mem.get("systemPercent"),
                "memory_metric_statuses": mem.get("metricStatuses", {}),
                "disk_percent": disk.get("totalUsagePercent"),
                "disk_metric_statuses": disk.get("metricStatuses", {}),
                "interfaces": [
                    {
                        "interface_name": iface.get("physical_name") or iface.get("logical_name"),
                        "interface_type": iface.get("type"),
                        "operational_status": (iface.get("runtime") or {}).get(
                            "operational_status"
                        ),
                        "link_status": (iface.get("runtime") or {}).get("link_status"),
                        "duplex_mode": (iface.get("runtime") or {}).get("duplex"),
                        "metric_status": iface.get("metric_status", "NO_DATA"),
                    }
                    for iface in ifaces
                ],
                "interface_traffic": [
                    {
                        "name": iface.get("interfaceName") or iface.get("interface"),
                        "interface_id": iface.get("interfaceId") or iface.get("interface"),
                        "input_bytes_avg": iface.get("inputBytesAverage"),
                        "output_bytes_avg": iface.get("outputBytesAverage"),
                        "drop_packets_avg": iface.get("dropsAverage"),
                        "input_errors_avg": iface.get("inputErrorsAverage"),
                        "output_errors_avg": iface.get("outputErrorsAverage"),
                        "metric_status": iface.get("metricStatus", "NO_DATA"),
                    }
                    for iface in aggregate_ifaces
                ],
                "fan_rpm": [f.get("rpm") for f in load.get("fans", []) if f.get("rpm") is not None],
                "start_time": load.get("startTime"),
                "end_time": load.get("endTime"),
                "capabilities": d.get("capabilities", {}),
                "collection_errors": d.get("collection_errors", []),
            }
        )

    # Collect all alerts from all devices
    all_alerts = []
    for d in devices:
        for alert in d.get("alerts", []):
            all_alerts.append(
                {
                    "id": alert.get("id"),
                    "module_id": alert.get("module_id"),
                    "name": alert.get("name"),
                    "details": alert.get("details"),
                    "params": None,
                }
            )

    # Map VPN tunnel statuses from FMC raw format to frontend format
    tunnel_statuses = []
    for t in raw.get("tunnel_statuses", []):
        topo = t.get("vpnTopology") or {}
        peer_a = t.get("peerA") or {}
        peer_b = t.get("peerB") or {}
        peer_a_dev = peer_a.get("device") or {}
        peer_b_dev = peer_b.get("device") or {}
        peer_a_iface = peer_a.get("vpnInterface") or {}
        peer_b_iface = peer_b.get("vpnInterface") or {}

        tunnel_statuses.append(
            {
                "id": t.get("id"),
                "name": topo.get("name") or t.get("name") or t.get("id"),
                "state": t.get("state", "UNKNOWN"),
                "topology_type": topo.get("type"),
                "ike_v1_enabled": False,
                "ike_v2_enabled": True,
                "route_based": topo.get("routeBased", False),
                "total_tunnels": 1,
                "active_tunnels": 1 if t.get("state") == "TUNNEL_UP" else 0,
                "down_tunnels": 1 if t.get("state") == "TUNNEL_DOWN" else 0,
                "unknown_tunnels": 1 if t.get("state") not in ("TUNNEL_UP", "TUNNEL_DOWN") else 0,
                "peer_a": {
                    "device_id": peer_a_dev.get("id"),
                    "device_name": peer_a_dev.get("name"),
                    "ip_addresses": [peer_a_iface.get("ipAddress")]
                    if peer_a_iface.get("ipAddress")
                    else [],
                    "vpn_interface": {
                        "name": peer_a_iface.get("name"),
                        "ip_address": peer_a_iface.get("ipAddress"),
                        "public_ip": None,
                        "interface_type": peer_a_iface.get("interfaceType"),
                    }
                    if peer_a_iface
                    else None,
                    "role": peer_a.get("role"),
                    "peer_type": peer_a.get("peerType"),
                },
                "peer_b": {
                    "device_id": peer_b_dev.get("id"),
                    "device_name": peer_b_dev.get("name"),
                    "ip_addresses": [peer_b_iface.get("ipAddress")]
                    if peer_b_iface.get("ipAddress")
                    else [],
                    "vpn_interface": {
                        "name": peer_b_iface.get("name"),
                        "ip_address": peer_b_iface.get("ipAddress"),
                        "public_ip": None,
                        "interface_type": peer_b_iface.get("interfaceType"),
                    }
                    if peer_b_iface
                    else None,
                    "role": peer_b.get("role"),
                    "peer_type": peer_b.get("peerType"),
                },
                "peer_a_detail": None,
                "peer_b_detail": None,
                "last_change": t.get("lastChange"),
                "message": t.get("message"),
            }
        )

    # Map VPN tunnel summaries
    tunnel_summaries = []
    for s in raw.get("tunnel_summaries", []):
        group = s.get("group") or {}
        tunnel_summaries.append(
            {
                "group_name": group.get("name") or s.get("name") or "All Tunnels",
                "group_type": group.get("type") or "aggregate",
                "tunnel_count": s.get("tunnelCount", 0),
                "tunnel_up_count": s.get("tunnelUpCount", 0),
                "tunnel_down_count": s.get("tunnelDownCount", 0),
                "tunnel_unknown_count": s.get("tunnelUnknownCount", 0),
            }
        )

    return {
        "collected_at": raw.get("collected_at"),
        "reset_status": raw.get("reset_status", {"state": "idle"}),
        "source_freshness": raw.get("source_freshness", []),
        "tunnel_statuses": tunnel_statuses,
        "tunnel_summaries": tunnel_summaries,
        "devices": fmc_devices,
        "aggregate_metrics": aggregate_metrics,
        "alerts": all_alerts,
        "tunnel_up": raw.get("tunnel_up", 0),
        "tunnel_down": raw.get("tunnel_down", 0),
        "tunnel_unknown": raw.get("tunnel_unknown", 0),
        "devices_connected": raw.get("devices_connected", 0),
        "devices_total": raw.get("total_devices", 0),
        "alerts_count": raw.get("alerts_total", 0),
    }


@router.get("/monitoring/policy-analysis")
async def get_policy_analysis(
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcMonitoringService, Depends(_get_fmc_service)],
) -> dict[str, Any]:
    """Return the latest scheduled read-only access-policy analysis."""
    dashboard = await service.get_dashboard()
    return dashboard.policy_analysis


@router.get("/monitoring/dashboard")
async def get_dashboard(
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcMonitoringService, Depends(_get_fmc_service)],
) -> dict[str, Any]:
    """Full FMC monitoring dashboard — one call, all data."""
    if not service.collector.client.configured:
        return {"status": "not_configured", "message": "FMC not configured"}
    try:
        dashboard = await service.get_dashboard()
        raw = dashboard.model_dump()
        return _map_dashboard(raw)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FMC error: {exc}") from exc


@router.get("/monitoring/events")
async def monitoring_events(
    request: Request,
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcMonitoringService, Depends(_get_fmc_service)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """SSE invalidation stream; dashboards still fetch bounded local-state payloads."""

    async def stream() -> AsyncIterator[str]:
        global _sse_clients
        _sse_clients += 1
        previous_id = last_event_id
        heartbeat_at = datetime.now(UTC)
        try:
            while not await request.is_disconnected():
                dashboard = await service.get_dashboard()
                event_id = dashboard.collected_at
                if event_id and event_id != previous_id:
                    payload = {
                        "type": "dashboard_updated",
                        "collected_at": event_id,
                        "source_freshness": [
                            item.model_dump(mode="json") for item in dashboard.source_freshness
                        ],
                    }
                    yield f"id: {event_id}\nevent: dashboard\ndata: {json.dumps(payload)}\n\n"
                    previous_id = event_id
                    heartbeat_at = datetime.now(UTC)
                elif (datetime.now(UTC) - heartbeat_at).total_seconds() >= 15:
                    yield f": heartbeat {datetime.now(UTC).isoformat()}\n\n"
                    heartbeat_at = datetime.now(UTC)
                await asyncio.sleep(2)
        finally:
            _sse_clients = max(0, _sse_clients - 1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def sse_client_count() -> int:
    return _sse_clients


@router.post("/monitoring/reset")
async def reset_monitoring_data(
    request: Request,
    _: Annotated[dict, Depends(get_current_user)],
) -> dict[str, Any]:
    """Queue a destructive FMC monitoring reset and sequential full refetch."""
    scheduler = getattr(request.app.state, "scanner_scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scanner scheduler not initialized")
    result = await scheduler.trigger_fmc_reset()
    if result.get("status") == "not_configured":
        raise HTTPException(status_code=400, detail="FMC is not configured")
    return result


@router.get("/monitoring/devices/{device_id}/metrics")
async def get_device_metric_history(
    device_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    metric_names: Annotated[list[str] | None, Query()] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    period_end = end or datetime.now(UTC)
    period_start = start or period_end - timedelta(hours=24)
    return await MonitoringHistoryService(session).metric_series(
        device_id=device_id,
        metric_names=metric_names or [],
        start=period_start,
        end=period_end,
        limit=limit,
        offset=offset,
    )


@router.get("/monitoring/vpn/{tunnel_id}/timeline")
async def get_vpn_timeline(
    tunnel_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    period_end = end or datetime.now(UTC)
    period_start = start or period_end - timedelta(days=30)
    return await MonitoringHistoryService(session).vpn_timeline(
        tunnel_id=tunnel_id,
        start=period_start,
        end=period_end,
        limit=limit,
        offset=offset,
    )


@router.get("/monitoring/ha/pairs")
async def get_ha_pairs(
    _: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    return {"items": await MonitoringHistoryService(session).ha_pairs()}


@router.get("/monitoring/health-alerts")
async def get_health_alerts(
    _: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    device_id: str | None = None,
    module_id: str | None = None,
    severity: str | None = None,
    lifecycle: str | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return await MonitoringHistoryService(session).alerts(
        device_id=device_id,
        module_id=module_id,
        severity=severity,
        lifecycle=lifecycle,
        search=search,
        limit=limit,
        offset=offset,
    )
