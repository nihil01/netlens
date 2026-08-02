"""Business queries over persisted NOC history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.monitoring.models import (
    FmcDeviceCurrent,
    HaPairCurrent,
    HealthAlertCurrent,
    MetricSample,
    VpnTunnelCurrent,
    VpnTunnelTransition,
)
from app.monitoring.vpn import (
    TunnelTransition,
    calculate_service_metrics,
    normalize_tunnel_state,
)

_MAX_ANALYTICS_TRANSITIONS = 100_000


class MonitoringHistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def metric_series(
        self,
        *,
        device_id: str,
        metric_names: list[str],
        start: datetime,
        end: datetime,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        filters = [
            MetricSample.device_id == device_id,
            MetricSample.timestamp >= start,
            MetricSample.timestamp <= end,
        ]
        if metric_names:
            filters.append(MetricSample.metric_name.in_(metric_names))
        total = await self.session.scalar(select(func.count(MetricSample.id)).where(*filters))
        result = await self.session.execute(
            select(MetricSample)
            .where(*filters)
            .order_by(MetricSample.timestamp.asc())
            .offset(offset)
            .limit(limit)
        )
        items = [
            {
                "timestamp": item.timestamp,
                "domain_id": item.domain_id,
                "device_id": item.device_id,
                "interface_id": item.interface_id,
                "ha_pair_id": item.ha_pair_id,
                "vpn_tunnel_id": item.vpn_tunnel_id,
                "metric_name": item.metric_name,
                "metric_value": item.metric_value,
                "metric_status": item.metric_status,
                "source": item.source,
                "window": item.metric_window,
                "collection_run_id": item.collection_run_id,
            }
            for item in result.scalars()
        ]
        return {"items": items, "total": int(total or 0), "limit": limit, "offset": offset}

    async def vpn_timeline(
        self,
        *,
        tunnel_id: str,
        start: datetime,
        end: datetime,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        current = await self.session.get(VpnTunnelCurrent, tunnel_id)
        if current is None:
            return {"tunnel": None, "transitions": [], "analytics": None, "total": 0}
        filters = [
            VpnTunnelTransition.tunnel_id == tunnel_id,
            VpnTunnelTransition.changed_at >= start,
            VpnTunnelTransition.changed_at <= end,
        ]
        total = await self.session.scalar(
            select(func.count(VpnTunnelTransition.id)).where(*filters)
        )
        page_result = await self.session.execute(
            select(VpnTunnelTransition)
            .where(*filters)
            .order_by(VpnTunnelTransition.changed_at.asc())
            .offset(offset)
            .limit(limit)
        )
        persisted = list(page_result.scalars())
        analytics_result = await self.session.execute(
            select(VpnTunnelTransition)
            .where(*filters)
            .order_by(VpnTunnelTransition.changed_at.asc())
            .limit(_MAX_ANALYTICS_TRANSITIONS + 1)
        )
        analytics_rows = list(analytics_result.scalars())
        analytics_truncated = len(analytics_rows) > _MAX_ANALYTICS_TRANSITIONS
        analytics_rows = analytics_rows[:_MAX_ANALYTICS_TRANSITIONS]
        transitions = [
            TunnelTransition(
                previous_status=normalize_tunnel_state(item.previous_status),
                new_status=normalize_tunnel_state(item.new_status),
                changed_at=item.changed_at,
                duration_in_previous_state_seconds=(item.duration_in_previous_state_seconds),
            )
            for item in analytics_rows
        ]
        first = analytics_rows[0] if analytics_rows else None
        prior_result = await self.session.execute(
            select(VpnTunnelTransition)
            .where(
                VpnTunnelTransition.tunnel_id == tunnel_id,
                VpnTunnelTransition.changed_at <= start,
            )
            .order_by(VpnTunnelTransition.changed_at.desc())
            .limit(1)
        )
        prior = prior_result.scalars().first()
        initial_status = (
            prior.new_status
            if prior
            else first.previous_status
            if first
            else current.current_status
            if current.state_changed_at <= start
            else "UNKNOWN"
        )
        analytics = calculate_service_metrics(
            transitions,
            period_start=start,
            period_end=end,
            initial_status=initial_status,
        )
        return {
            "tunnel": {
                "id": current.tunnel_id,
                "name": current.name,
                "peer": current.peer,
                "device_id": current.device_id,
                "policy": current.policy,
                "current_status": current.current_status,
                "is_flapping": current.is_flapping,
                "first_seen_at": current.first_seen_at,
                "last_seen_at": current.last_seen_at,
                "last_up_at": current.last_up_at,
                "last_down_at": current.last_down_at,
                "transition_count": current.transition_count,
                "flap_count": current.flap_count,
            },
            "transitions": [
                {
                    "previous_status": item.previous_status,
                    "new_status": item.new_status,
                    "changed_at": item.changed_at,
                    "duration_in_previous_state_seconds": (item.duration_in_previous_state_seconds),
                }
                for item in persisted
            ],
            "analytics": analytics.__dict__,
            "analytics_truncated": analytics_truncated,
            "total": int(total or 0),
            "limit": limit,
            "offset": offset,
        }

    async def ha_pairs(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(HaPairCurrent).order_by(HaPairCurrent.name.asc())
        )
        pairs = list(result.scalars())
        member_ids = {
            str(device_id)
            for pair in pairs
            for device_id in (
                pair.primary_device_id,
                pair.secondary_device_id,
                pair.active_member_id,
                pair.standby_member_id,
            )
            if device_id
        }
        names: dict[str, str] = {}
        if member_ids:
            devices = await self.session.execute(
                select(
                    FmcDeviceCurrent.device_id,
                    FmcDeviceCurrent.name,
                    FmcDeviceCurrent.host_name,
                ).where(FmcDeviceCurrent.device_id.in_(member_ids))
            )
            names = {
                str(device_id): name or host_name or str(device_id)
                for device_id, name, host_name in devices.all()
            }
        return [
            {
                "pair_id": item.pair_id,
                "name": item.name,
                "pair_state": item.pair_state,
                "health_status": item.health_status,
                "health_message": item.health_message,
                "primary_device_id": item.primary_device_id,
                "primary_device_name": names.get(str(item.primary_device_id)),
                "secondary_device_id": item.secondary_device_id,
                "secondary_device_name": names.get(str(item.secondary_device_id)),
                "active_member_id": item.active_member_id,
                "active_member_name": names.get(str(item.active_member_id))
                if item.active_member_id
                else None,
                "standby_member_id": item.standby_member_id,
                "standby_member_name": names.get(str(item.standby_member_id))
                if item.standby_member_id
                else None,
                "failover_link": item.failover_link,
                "stateful_link": item.stateful_link,
                "monitored_interfaces": item.monitored_interfaces,
                "last_role_transition_at": item.last_role_transition_at,
                "last_health_transition_at": item.last_health_transition_at,
                "last_seen_at": item.last_seen_at,
            }
            for item in pairs
        ]

    async def alerts(
        self,
        *,
        device_id: str | None,
        module_id: str | None,
        severity: str | None,
        lifecycle: str | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        filters = []
        if device_id:
            filters.append(HealthAlertCurrent.device_id == device_id)
        if module_id:
            filters.append(HealthAlertCurrent.module_id == module_id)
        if severity:
            filters.append(HealthAlertCurrent.severity == severity.upper())
        if lifecycle:
            filters.append(HealthAlertCurrent.lifecycle_state == lifecycle.upper())
        if search:
            filters.append(
                HealthAlertCurrent.description.ilike(f"%{search}%")
                | HealthAlertCurrent.details.ilike(f"%{search}%")
            )
        total = await self.session.scalar(
            select(func.count(HealthAlertCurrent.alert_id)).where(*filters)
        )
        result = await self.session.execute(
            select(HealthAlertCurrent)
            .where(*filters)
            .order_by(HealthAlertCurrent.last_seen_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return {
            "items": [
                {
                    "alert_id": item.alert_id,
                    "device_id": item.device_id,
                    "module_id": item.module_id,
                    "severity": item.severity,
                    "source_status": item.source_status,
                    "lifecycle_state": item.lifecycle_state,
                    "description": item.description,
                    "details": item.details,
                    "first_seen_at": item.first_seen_at,
                    "last_seen_at": item.last_seen_at,
                    "resolved_at": item.resolved_at,
                    "reopen_count": item.reopen_count,
                    "repeat_count": item.repeat_count,
                }
                for item in result.scalars()
            ],
            "total": int(total or 0),
            "limit": limit,
            "offset": offset,
        }


def default_history_window() -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    return end - timedelta(hours=24), end
