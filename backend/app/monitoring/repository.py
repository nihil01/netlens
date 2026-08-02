"""Persistence repository for normalized NOC current state and metric history."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.fmc.schemas import CollectedDevice, MetricStatus, MonitoringDashboard
from app.monitoring.alerts import AlertLifecycle, next_alert_lifecycle
from app.monitoring.models import (
    CollectorRun,
    FmcDeviceCurrent,
    HaPairCurrent,
    HaRoleTransition,
    HealthAlertCurrent,
    HealthAlertObservation,
    MetricSample,
    NetboxFmcCorrelation,
    RawFmcResponse,
    SourceFreshnessState,
    VpnTunnelCurrent,
    VpnTunnelTransition,
)
from app.monitoring.vpn import detect_transition, normalize_tunnel_state
from app.observability.metrics import increment

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


class MonitoringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def clear_fmc_monitoring_data(self) -> dict[str, int]:
        """Delete FMC monitoring state/history while preserving the FMC audit trail."""
        models = (
            HealthAlertObservation,
            VpnTunnelTransition,
            HaRoleTransition,
            MetricSample,
            RawFmcResponse,
            HealthAlertCurrent,
            VpnTunnelCurrent,
            HaPairCurrent,
            FmcDeviceCurrent,
            NetboxFmcCorrelation,
        )
        deleted: dict[str, int] = {}
        for model in models:
            result = await self.session.execute(delete(model))
            deleted[model.__tablename__] = int(result.rowcount or 0)

        collector_runs = await self.session.execute(
            delete(CollectorRun).where(CollectorRun.source == "fmc")
        )
        deleted[CollectorRun.__tablename__] = int(collector_runs.rowcount or 0)
        freshness = await self.session.execute(
            delete(SourceFreshnessState).where(SourceFreshnessState.source.like("fmc_%"))
        )
        deleted[SourceFreshnessState.__tablename__] = int(freshness.rowcount or 0)
        return deleted

    async def persist_fmc_dashboard(
        self,
        dashboard: MonitoringDashboard,
        raw_responses: list[dict[str, Any]],
        *,
        raw_retention_days: int,
        alert_flap_reopen_threshold: int = 3,
        collector_name: str = "fmc_device_health",
        persist_metrics: bool = True,
        persist_alerts: bool = True,
        persist_ha: bool = True,
    ) -> None:
        if not dashboard.collection_run_id or not dashboard.domain_id or not dashboard.collected_at:
            raise ValueError("dashboard requires collection_run_id, domain_id, and collected_at")
        collected_at = _timestamp(dashboard.collected_at)
        partial = (
            bool(dashboard.collection_errors)
            or any(device.collection_errors for device in dashboard.devices)
            or any(pair.collection_errors for pair in dashboard.ha_pairs)
        )
        records_received = (
            len(dashboard.ha_pairs) if collector_name == "fmc_ha" else dashboard.total_devices
        )
        if collector_name == "fmc_policy":
            records_received = int(dashboard.policy_analysis.get("total_policies", 0))
        run_values = {
            "id": dashboard.collection_run_id,
            "collector": collector_name,
            "source": "fmc",
            "started_at": collected_at,
            "finished_at": datetime.now(UTC),
            "status": "PARTIAL" if partial else "SUCCESS",
            "partial_result": partial,
            "records_received": records_received,
            "metadata_json": {
                "domain_id": dashboard.domain_id,
                "devices_connected": dashboard.devices_connected,
            },
        }
        await self.session.execute(insert(CollectorRun).values(**run_values))

        metric_rows: list[dict[str, Any]] = []
        for collected_device in dashboard.devices:
            await self._upsert_device(
                collected_device,
                dashboard.collection_run_id,
                collected_at,
            )
            if persist_metrics:
                metric_rows.extend(
                    metric_rows_for_device(
                        collected_device,
                        dashboard.collection_run_id,
                        collected_at,
                    )
                )
        if metric_rows:
            await self.session.execute(insert(MetricSample), metric_rows)
            increment(
                "device_metrics_missing_total",
                sum(
                    1
                    for row in metric_rows
                    if row["metric_status"] in {"NO_DATA", "AVAILABLE_NO_DATA", "INVALID_RESPONSE"}
                ),
            )

        if persist_alerts:
            await self._persist_alerts(
                dashboard,
                collected_at,
                alert_flap_reopen_threshold=alert_flap_reopen_threshold,
            )
        if persist_ha:
            await self._persist_ha_pairs(dashboard, collected_at)

        expires_at = collected_at + timedelta(days=max(1, raw_retention_days))
        raw_rows = [
            _raw_row(item, dashboard.collection_run_id, collected_at, expires_at)
            for item in raw_responses
        ]
        if raw_rows:
            await self.session.execute(insert(RawFmcResponse), raw_rows)

    async def _persist_ha_pairs(
        self,
        dashboard: MonitoringDashboard,
        observed_at: datetime,
    ) -> None:
        if not dashboard.domain_id or not dashboard.collection_run_id:
            return
        pair_ids = [pair.id for pair in dashboard.ha_pairs if pair.id]
        existing: dict[str, HaPairCurrent] = {}
        if pair_ids:
            result = await self.session.execute(
                select(HaPairCurrent).where(HaPairCurrent.pair_id.in_(pair_ids))
            )
            existing = {item.pair_id: item for item in result.scalars()}
        ha_metric_rows: list[dict[str, Any]] = []
        for pair in dashboard.ha_pairs:
            if not pair.id or not pair.primary.device_id or not pair.secondary.device_id:
                continue
            previous = existing.get(pair.id)
            role_transition = bool(
                previous
                and previous.active_member_id
                and pair.active_member_id
                and previous.active_member_id != pair.active_member_id
            )
            if role_transition:
                await self.session.execute(
                    insert(HaRoleTransition),
                    [
                        {
                            "domain_id": dashboard.domain_id,
                            "pair_id": pair.id,
                            "device_id": previous.active_member_id,
                            "previous_role": "ACTIVE",
                            "new_role": "STANDBY",
                            "changed_at": observed_at,
                            "collection_run_id": dashboard.collection_run_id,
                            "raw_json": pair.raw,
                        },
                        {
                            "domain_id": dashboard.domain_id,
                            "pair_id": pair.id,
                            "device_id": pair.active_member_id,
                            "previous_role": "STANDBY",
                            "new_role": "ACTIVE",
                            "changed_at": observed_at,
                            "collection_run_id": dashboard.collection_run_id,
                            "raw_json": pair.raw,
                        },
                    ],
                )
            health_transition = bool(previous and previous.health_status != pair.health_status)
            values = {
                "pair_id": pair.id,
                "domain_id": dashboard.domain_id,
                "name": pair.name,
                "pair_state": pair.pair_state,
                "health_status": pair.health_status,
                "health_message": pair.health_message,
                "primary_device_id": pair.primary.device_id,
                "secondary_device_id": pair.secondary.device_id,
                "active_member_id": pair.active_member_id,
                "standby_member_id": pair.standby_member_id,
                "failover_link": pair.failover_link,
                "stateful_link": pair.stateful_link,
                "monitored_interfaces": [
                    interface.model_dump(mode="json") for interface in pair.monitored_interfaces
                ],
                "last_role_transition_at": (
                    observed_at
                    if role_transition
                    else previous.last_role_transition_at
                    if previous
                    else None
                ),
                "last_health_transition_at": (
                    observed_at
                    if health_transition
                    else previous.last_health_transition_at
                    if previous
                    else None
                ),
                "first_seen_at": previous.first_seen_at if previous else observed_at,
                "last_seen_at": observed_at,
                "raw_json": pair.raw,
            }
            statement = insert(HaPairCurrent).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[HaPairCurrent.pair_id],
                set_={key: value for key, value in values.items() if key != "pair_id"},
            )
            await self.session.execute(statement)

            pair_value = {
                "HEALTHY": 1.0,
                "DEGRADED": 0.5,
                "FAILED": 0.0,
            }.get(pair.pair_state)
            ha_metric_rows.append(
                {
                    "timestamp": observed_at,
                    "domain_id": dashboard.domain_id,
                    "ha_pair_id": pair.id,
                    "metric_name": "HA.pair.status",
                    "metric_value": pair_value,
                    "metric_status": (
                        MetricStatus.VALUE_ZERO.value
                        if pair_value == 0
                        else MetricStatus.VALUE.value
                        if pair_value is not None
                        else MetricStatus.NO_DATA.value
                    ),
                    "source": "fmc_ha",
                    "collection_run_id": dashboard.collection_run_id,
                }
            )
            for member_id, runtime_role in (
                (pair.primary.device_id, pair.primary.runtime_role),
                (pair.secondary.device_id, pair.secondary.runtime_role),
            ):
                role_value = (
                    1.0
                    if str(runtime_role or "").upper() == "ACTIVE"
                    else 0.0
                    if str(runtime_role or "").upper() == "STANDBY"
                    else None
                )
                ha_metric_rows.append(
                    {
                        "timestamp": observed_at,
                        "domain_id": dashboard.domain_id,
                        "device_id": member_id,
                        "ha_pair_id": pair.id,
                        "metric_name": "HA.member.status",
                        "metric_value": role_value,
                        "metric_status": (
                            MetricStatus.VALUE_ZERO.value
                            if role_value == 0
                            else MetricStatus.VALUE.value
                            if role_value is not None
                            else MetricStatus.NO_DATA.value
                        ),
                        "source": "fmc_ha",
                        "collection_run_id": dashboard.collection_run_id,
                    }
                )
        if ha_metric_rows:
            await self.session.execute(insert(MetricSample), ha_metric_rows)

    async def _persist_alerts(
        self,
        dashboard: MonitoringDashboard,
        observed_at: datetime,
        *,
        alert_flap_reopen_threshold: int,
    ) -> None:
        if not dashboard.domain_id or not dashboard.collection_run_id:
            return
        result = await self.session.execute(
            select(HealthAlertCurrent).where(HealthAlertCurrent.domain_id == dashboard.domain_id)
        )
        existing = {item.alert_id: item for item in result.scalars()}
        seen_ids: set[str] = set()
        for device in dashboard.devices:
            for alert in device.alerts:
                if not alert.id:
                    continue
                alert_id = str(alert.id)
                seen_ids.add(alert_id)
                previous = existing.get(alert_id)
                previous_state = previous.lifecycle_state if previous else None
                previous_reopens = previous.reopen_count if previous else 0
                lifecycle = next_alert_lifecycle(
                    previous_state,
                    observed_active=True,
                    reopen_count=previous_reopens,
                    flapping_reopen_threshold=alert_flap_reopen_threshold,
                )
                reopened = previous_state == AlertLifecycle.RESOLVED.value
                values = {
                    "alert_id": alert_id,
                    "domain_id": dashboard.domain_id,
                    "device_id": alert.device_uuid or device.device.id,
                    "module_id": alert.module_id,
                    "severity": alert.status,
                    "source_status": alert.status,
                    "lifecycle_state": lifecycle.value,
                    "description": alert.name,
                    "details": alert.details,
                    "first_seen_at": previous.first_seen_at if previous else observed_at,
                    "last_seen_at": observed_at,
                    "resolved_at": None,
                    "reopen_count": previous_reopens + (1 if reopened else 0),
                    "repeat_count": (previous.repeat_count + 1) if previous else 1,
                    "raw_json": alert.raw,
                }
                statement = insert(HealthAlertCurrent).values(**values)
                statement = statement.on_conflict_do_update(
                    index_elements=[HealthAlertCurrent.alert_id],
                    set_={key: value for key, value in values.items() if key != "alert_id"},
                )
                await self.session.execute(statement)
                await self.session.execute(
                    insert(HealthAlertObservation).values(
                        alert_id=alert_id,
                        observed_at=observed_at,
                        lifecycle_state=lifecycle.value,
                        severity=alert.status,
                        source_status=alert.status,
                        collection_run_id=dashboard.collection_run_id,
                        raw_json=alert.raw,
                    )
                )

        alerts_complete = bool(dashboard.devices) and all(
            device.capabilities.get("healthAlerts")
            in {"SUPPORTED", MetricStatus.AVAILABLE_NO_DATA.value}
            for device in dashboard.devices
        )
        if not alerts_complete:
            return
        for alert_id, previous in existing.items():
            if alert_id in seen_ids or previous.lifecycle_state == AlertLifecycle.RESOLVED.value:
                continue
            await self.session.execute(
                update(HealthAlertCurrent)
                .where(HealthAlertCurrent.alert_id == alert_id)
                .values(
                    lifecycle_state=AlertLifecycle.RESOLVED.value,
                    resolved_at=observed_at,
                )
            )
            await self.session.execute(
                insert(HealthAlertObservation).values(
                    alert_id=alert_id,
                    observed_at=observed_at,
                    lifecycle_state=AlertLifecycle.RESOLVED.value,
                    severity=previous.severity,
                    source_status=previous.source_status,
                    collection_run_id=dashboard.collection_run_id,
                    raw_json=previous.raw_json,
                )
            )

    async def _upsert_device(
        self,
        collected: CollectedDevice,
        collection_run_id: str,
        collected_at: datetime,
    ) -> None:
        device = collected.device
        if not collected.domain_id or not device.id:
            return
        values = {
            "domain_id": collected.domain_id,
            "device_id": device.id,
            "name": device.name,
            "host_name": device.host_name,
            "management_ip": device.raw.get("hostName"),
            "model": device.model,
            "model_number": device.model_number,
            "software_version": device.sw_version,
            "serial_number": device.serial_number,
            "is_connected": device.is_connected,
            "health_status": device.health_status,
            "health_message": device.health_message,
            "deployment_status": device.deployment_status,
            "role": device.role,
            "status": device.status,
            "health_policy": device.health_policy,
            "access_policy": device.access_policy,
            "is_dummy_device": device.is_dummy_device,
            "is_part_of_container": device.is_part_of_container,
            "container_details": device.container_details,
            "capabilities": collected.capabilities,
            "aggregate_status": collected.aggregate_status.value,
            "raw_json": device.raw,
            "last_collection_run_id": collection_run_id,
            "last_seen_at": collected_at,
        }
        statement = insert(FmcDeviceCurrent).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_fmc_device_domain_device",
            set_={
                key: value for key, value in values.items() if key not in {"domain_id", "device_id"}
            },
        )
        await self.session.execute(statement)

    async def upsert_source_freshness(self, freshness: dict[str, Any]) -> None:
        values = {
            **freshness,
            "last_attempt": _optional_timestamp(freshness.get("last_attempt")),
            "last_success": _optional_timestamp(freshness.get("last_success")),
            "updated_at": datetime.now(UTC),
        }
        statement = insert(SourceFreshnessState).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[SourceFreshnessState.source],
            set_={key: value for key, value in values.items() if key != "source"},
        )
        await self.session.execute(statement)

    async def persist_vpn_snapshot(
        self,
        *,
        domain_id: str,
        tunnels: list[dict[str, Any]],
        observed_at: datetime,
        raw_responses: list[dict[str, Any]],
        raw_retention_days: int,
        flap_threshold: int,
        flap_window_seconds: int,
        partial_error: str | None = None,
    ) -> str:
        collection_run_id = str(uuid4())
        await self.session.execute(
            insert(CollectorRun).values(
                id=collection_run_id,
                collector="fmc_vpn",
                source="fmc",
                started_at=observed_at,
                finished_at=datetime.now(UTC),
                status="PARTIAL" if partial_error else "SUCCESS",
                partial_result=bool(partial_error),
                records_received=len(tunnels),
                error=partial_error,
            )
        )
        tunnel_ids = [str(raw.get("id")) for raw in tunnels if raw.get("id")]
        existing: dict[str, VpnTunnelCurrent] = {}
        recent_transition_counts: dict[str, int] = {}
        if tunnel_ids:
            result = await self.session.execute(
                select(VpnTunnelCurrent).where(VpnTunnelCurrent.tunnel_id.in_(tunnel_ids))
            )
            existing = {item.tunnel_id: item for item in result.scalars()}
            recent_result = await self.session.execute(
                select(VpnTunnelTransition.tunnel_id, func.count(VpnTunnelTransition.id))
                .where(
                    VpnTunnelTransition.tunnel_id.in_(tunnel_ids),
                    VpnTunnelTransition.changed_at
                    >= observed_at - timedelta(seconds=flap_window_seconds),
                )
                .group_by(VpnTunnelTransition.tunnel_id)
            )
            recent_transition_counts = {
                tunnel_id: int(count) for tunnel_id, count in recent_result.all()
            }

        for raw in tunnels:
            tunnel_id = str(raw.get("id") or "")
            if not tunnel_id:
                continue
            status = normalize_tunnel_state(raw.get("state"))
            previous = existing.get(tunnel_id)
            state_changed_at = previous.state_changed_at if previous else observed_at
            transition_count = previous.transition_count if previous else 0
            flap_count = previous.flap_count if previous else 0
            is_flapping = recent_transition_counts.get(tunnel_id, 0) >= flap_threshold
            last_up_at = previous.last_up_at if previous else None
            last_down_at = previous.last_down_at if previous else None
            if previous:
                transition = detect_transition(
                    previous.current_status,
                    status,
                    changed_at=observed_at,
                    previous_changed_at=previous.state_changed_at,
                )
                if transition:
                    await self.session.execute(
                        insert(VpnTunnelTransition).values(
                            tunnel_id=tunnel_id,
                            previous_status=transition.previous_status.value,
                            new_status=transition.new_status.value,
                            changed_at=transition.changed_at,
                            duration_in_previous_state_seconds=(
                                transition.duration_in_previous_state_seconds
                            ),
                            collection_run_id=collection_run_id,
                        )
                    )
                    transition_count += 1
                    state_changed_at = observed_at
                    recent_transition_counts[tunnel_id] = (
                        recent_transition_counts.get(tunnel_id, 0) + 1
                    )
                    is_flapping = recent_transition_counts[tunnel_id] >= flap_threshold
                    if is_flapping and not previous.is_flapping:
                        flap_count += 1
            if status.value == "UP":
                last_up_at = observed_at
            elif status.value == "DOWN":
                last_down_at = observed_at

            topology = raw.get("vpnTopology") if isinstance(raw.get("vpnTopology"), dict) else {}
            peer_b = raw.get("peerB") if isinstance(raw.get("peerB"), dict) else {}
            peer_b_interface = (
                peer_b.get("vpnInterface") if isinstance(peer_b.get("vpnInterface"), dict) else {}
            )
            peer_a = raw.get("peerA") if isinstance(raw.get("peerA"), dict) else {}
            peer_a_device = peer_a.get("device") if isinstance(peer_a.get("device"), dict) else {}
            values = {
                "tunnel_id": tunnel_id,
                "domain_id": domain_id,
                "name": topology.get("name") or raw.get("name") or tunnel_id,
                "peer": peer_b_interface.get("ipAddress") or peer_b.get("name"),
                "device_id": peer_a_device.get("id"),
                "policy": topology.get("name"),
                "current_status": status.value,
                "is_flapping": is_flapping,
                "first_seen_at": previous.first_seen_at if previous else observed_at,
                "last_seen_at": observed_at,
                "state_changed_at": state_changed_at,
                "last_up_at": last_up_at,
                "last_down_at": last_down_at,
                "transition_count": transition_count,
                "flap_count": flap_count,
                "raw_json": raw,
            }
            statement = insert(VpnTunnelCurrent).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[VpnTunnelCurrent.tunnel_id],
                set_={key: value for key, value in values.items() if key != "tunnel_id"},
            )
            await self.session.execute(statement)

        expires_at = observed_at + timedelta(days=max(1, raw_retention_days))
        raw_rows = [
            _raw_row(item, collection_run_id, observed_at, expires_at) for item in raw_responses
        ]
        if raw_rows:
            await self.session.execute(insert(RawFmcResponse), raw_rows)
        return collection_run_id


def metric_rows_for_device(
    collected: CollectedDevice,
    collection_run_id: str,
    timestamp: datetime,
) -> list[dict[str, Any]]:
    if not collected.domain_id or not collected.device.id:
        return []
    load = collected.load
    source = str(load.get("source") or "health_aggregatemetrics")
    window = load.get("metricWindow")
    rows: list[dict[str, Any]] = []
    scalar_blocks = {
        "cpu": {
            "linaPercent": "cpu.lina",
            "snortPercent": "cpu.snort",
            "systemPercent": "cpu.system",
        },
        "memory": {
            "linaPercent": "memory.lina",
            "snortPercent": "memory.snort",
            "systemPercent": "memory.system",
        },
        "disk": {"totalUsagePercent": "disk.usage"},
    }
    for block_name, fields in scalar_blocks.items():
        block = load.get(block_name) if isinstance(load.get(block_name), dict) else {}
        statuses = (
            block.get("metricStatuses") if isinstance(block.get("metricStatuses"), dict) else {}
        )
        for field_name, metric_name in fields.items():
            value = _number(block.get(field_name))
            status = statuses.get(field_name) or (
                MetricStatus.VALUE_ZERO.value
                if value == 0
                else MetricStatus.VALUE.value
                if value is not None
                else collected.aggregate_status.value
            )
            rows.append(
                _metric_row(
                    collected,
                    collection_run_id,
                    timestamp,
                    metric_name,
                    value,
                    str(status),
                    source,
                    window,
                )
            )

    for fan in load.get("fans", []):
        if not isinstance(fan, dict):
            continue
        rows.append(
            _metric_row(
                collected,
                collection_run_id,
                timestamp,
                f"fan.rpm.{fan.get('name') or 'unknown'}",
                _number(fan.get("rpm")),
                str(fan.get("metricStatus") or MetricStatus.NO_DATA.value),
                source,
                window,
            )
        )

    aggregate_interfaces = load.get("interfaces")
    if not isinstance(aggregate_interfaces, list):
        aggregate_interfaces = []
    for interface in aggregate_interfaces:
        if not isinstance(interface, dict):
            continue
        interface_id = (
            interface.get("interfaceId")
            or interface.get("interface")
            or interface.get("interfaceName")
        )
        if not interface_id:
            continue
        statuses = (
            interface.get("metricStatuses")
            if isinstance(interface.get("metricStatuses"), dict)
            else {}
        )
        aggregate_values = {
            "interface.link_status": (
                1.0
                if interface.get("linkStatus") == "UP"
                else 0.0
                if interface.get("linkStatus") == "DOWN"
                else None
            ),
            "interface.input_bytes_avg": interface.get("inputBytesAverage"),
            "interface.output_bytes_avg": interface.get("outputBytesAverage"),
            "interface.input_errors": interface.get("inputErrorsAverage"),
            "interface.output_errors": interface.get("outputErrorsAverage"),
            "interface.drops": interface.get("dropsAverage"),
        }
        normalized_names = {
            "interface.input_bytes_avg": "inputBytesAverage",
            "interface.output_bytes_avg": "outputBytesAverage",
            "interface.input_errors": "inputErrorsAverage",
            "interface.output_errors": "outputErrorsAverage",
            "interface.drops": "dropsAverage",
        }
        for metric_name, value in aggregate_values.items():
            numeric = _number(value)
            status = statuses.get(normalized_names.get(metric_name, "")) or (
                MetricStatus.VALUE_ZERO.value
                if numeric == 0
                else MetricStatus.VALUE.value
                if numeric is not None
                else str(interface.get("metricStatus") or MetricStatus.NO_DATA.value)
            )
            row = _metric_row(
                collected,
                collection_run_id,
                timestamp,
                metric_name,
                numeric,
                str(status),
                "health_aggregatemetrics",
                str(load.get("metricWindow") or "5m"),
            )
            row["interface_id"] = str(interface_id)
            rows.append(row)

    for interface in [] if aggregate_interfaces else collected.interfaces:
        runtime = interface.runtime
        interface_values = {
            "interface.link_status": (
                1.0
                if runtime.link_status == "UP"
                else 0.0
                if runtime.link_status == "DOWN"
                else None
            ),
            "interface.input_bytes_avg": runtime.input_bytes_average,
            "interface.output_bytes_avg": runtime.output_bytes_average,
            "interface.input_errors": runtime.input_errors_average,
            "interface.output_errors": runtime.output_errors_average,
            "interface.drops": runtime.drops_average,
        }
        for metric_name, value in interface_values.items():
            numeric = _number(value)
            status = (
                MetricStatus.VALUE_ZERO.value
                if numeric == 0
                else MetricStatus.VALUE.value
                if numeric is not None
                else interface.metric_status.value
            )
            row = _metric_row(
                collected,
                collection_run_id,
                timestamp,
                metric_name,
                numeric,
                status,
                "health_aggregatemetrics",
                runtime.metric_window,
            )
            row["interface_id"] = interface.id or interface.physical_name or interface.logical_name
            rows.append(row)
    return rows


def _metric_row(
    collected: CollectedDevice,
    collection_run_id: str,
    timestamp: datetime,
    metric_name: str,
    value: float | None,
    status: str,
    source: str,
    window: str | None,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "domain_id": collected.domain_id,
        "device_id": collected.device.id,
        "metric_name": metric_name,
        "metric_value": value,
        "metric_status": status,
        "source": source,
        "metric_window": window,
        "collection_run_id": collection_run_id,
    }


def _raw_row(
    item: dict[str, Any],
    collection_run_id: str,
    collected_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    endpoint = str(item.get("path") or "unknown")
    match = _UUID_RE.search(endpoint)
    return {
        "collection_run_id": collection_run_id,
        "collected_at": collected_at,
        "device_id": match.group(0) if match else None,
        "endpoint": endpoint,
        "http_status": item.get("status"),
        "duration_ms": item.get("duration_ms"),
        "response_bytes": item.get("response_bytes", 0),
        "items_count": item.get("items_count"),
        "error_category": item.get("error_category"),
        "payload": item.get("data"),
        "payload_omitted": bool(item.get("raw_omitted")),
        "expires_at": expires_at,
    }


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _optional_timestamp(value: Any) -> datetime | None:
    return _timestamp(value) if isinstance(value, str) and value else None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
