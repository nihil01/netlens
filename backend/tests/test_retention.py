from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.monitoring.retention import retention_cutoffs


def test_retention_cutoffs_are_independent_and_configurable() -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    settings = Settings(
        metric_retention_days=30,
        vpn_transition_retention_days=365,
        health_alert_retention_days=730,
        collector_run_retention_days=14,
    )

    cutoffs = retention_cutoffs(settings, now)

    assert cutoffs["metric_samples"] == now - timedelta(days=30)
    assert cutoffs["vpn_tunnel_transitions"] == now - timedelta(days=365)
    assert cutoffs["health_alert_observations"] == now - timedelta(days=730)
    assert cutoffs["collector_runs"] == now - timedelta(days=14)
