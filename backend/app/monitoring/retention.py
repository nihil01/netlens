"""Configurable retention for append-only NOC history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete

from app.core.config import Settings, get_settings
from app.db import session_scope
from app.monitoring.models import (
    CollectorRun,
    HealthAlertObservation,
    MetricSample,
    RawFmcResponse,
    VpnTunnelTransition,
)


class RetentionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def run(self, *, now: datetime | None = None) -> dict[str, Any]:
        reference = now or datetime.now(UTC)
        cutoffs = retention_cutoffs(self.settings, reference)
        async with session_scope() as session:
            statements = {
                "raw_fmc_responses": delete(RawFmcResponse).where(
                    RawFmcResponse.expires_at <= reference
                ),
                "metric_samples": delete(MetricSample).where(
                    MetricSample.timestamp < cutoffs["metric_samples"]
                ),
                "vpn_tunnel_transitions": delete(VpnTunnelTransition).where(
                    VpnTunnelTransition.changed_at < cutoffs["vpn_tunnel_transitions"]
                ),
                "health_alert_observations": delete(HealthAlertObservation).where(
                    HealthAlertObservation.observed_at < cutoffs["health_alert_observations"]
                ),
                "collector_runs": delete(CollectorRun).where(
                    CollectorRun.started_at < cutoffs["collector_runs"]
                ),
            }
            deleted = {}
            for table, statement in statements.items():
                result = await session.execute(statement)
                deleted[table] = max(0, result.rowcount or 0)
        return {
            "status": "ok",
            "ran_at": reference.isoformat(),
            "deleted": deleted,
            "cutoffs": {name: value.isoformat() for name, value in cutoffs.items()},
        }


def retention_cutoffs(settings: Settings, now: datetime) -> dict[str, datetime]:
    """Pure cutoff calculation, kept separate for deterministic tests."""
    return {
        "metric_samples": now - timedelta(days=max(1, settings.metric_retention_days)),
        "vpn_tunnel_transitions": now
        - timedelta(days=max(1, settings.vpn_transition_retention_days)),
        "health_alert_observations": now
        - timedelta(days=max(1, settings.health_alert_retention_days)),
        "collector_runs": now - timedelta(days=max(1, settings.collector_run_retention_days)),
    }
