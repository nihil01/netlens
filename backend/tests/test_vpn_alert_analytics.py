from datetime import UTC, datetime, timedelta

from app.monitoring.alerts import AlertLifecycle, next_alert_lifecycle
from app.monitoring.vpn import (
    TunnelState,
    TunnelTransition,
    calculate_service_metrics,
    detect_transition,
    is_flapping,
    normalize_tunnel_state,
)


def test_vpn_status_normalization_and_transition_duration() -> None:
    changed_at = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
    transition = detect_transition(
        "TUNNEL_UP",
        "TUNNEL_DOWN",
        changed_at=changed_at,
        previous_changed_at=changed_at - timedelta(hours=1),
    )

    assert normalize_tunnel_state("TUNNEL_UP") == TunnelState.UP
    assert transition is not None
    assert transition.previous_status == TunnelState.UP
    assert transition.new_status == TunnelState.DOWN
    assert transition.duration_in_previous_state_seconds == 3600


def test_vpn_transition_is_not_created_for_same_state() -> None:
    assert detect_transition("UP", "TUNNEL_UP", changed_at=datetime.now(UTC)) is None


def test_vpn_flapping_threshold_uses_rolling_window() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    transitions = [
        TunnelTransition(TunnelState.UP, TunnelState.DOWN, now - timedelta(minutes=14)),
        TunnelTransition(TunnelState.DOWN, TunnelState.UP, now - timedelta(minutes=8)),
        TunnelTransition(TunnelState.UP, TunnelState.DOWN, now - timedelta(minutes=1)),
    ]

    assert is_flapping(transitions, threshold=3, window_seconds=900, at=now) is True
    assert is_flapping(transitions, threshold=4, window_seconds=900, at=now) is False


def test_vpn_availability_mtbf_mttr_and_longest_outage() -> None:
    start = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    transitions = [
        TunnelTransition(TunnelState.UP, TunnelState.DOWN, start + timedelta(hours=2)),
        TunnelTransition(TunnelState.DOWN, TunnelState.UP, start + timedelta(hours=3)),
        TunnelTransition(TunnelState.UP, TunnelState.DOWN, start + timedelta(hours=7)),
        TunnelTransition(TunnelState.DOWN, TunnelState.UP, start + timedelta(hours=9)),
    ]

    metrics = calculate_service_metrics(
        transitions,
        period_start=start,
        period_end=start + timedelta(hours=10),
        initial_status=TunnelState.UP,
    )

    assert metrics.up_seconds == 7 * 3600
    assert metrics.down_seconds == 3 * 3600
    assert metrics.availability_percent == 70
    assert metrics.longest_outage_seconds == 2 * 3600
    assert metrics.mtbf_seconds == 3 * 3600
    assert metrics.mttr_seconds == 1.5 * 3600
    assert metrics.transition_count == 4


def test_unknown_vpn_time_is_not_reported_as_downtime() -> None:
    start = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    metrics = calculate_service_metrics(
        [],
        period_start=start,
        period_end=start + timedelta(hours=1),
    )

    assert metrics.availability_percent is None
    assert metrics.down_seconds == 0
    assert metrics.unknown_seconds == 3600


def test_alert_lifecycle_new_resolved_reopened_and_flapping() -> None:
    assert next_alert_lifecycle(None, observed_active=True) == AlertLifecycle.NEW
    assert (
        next_alert_lifecycle(AlertLifecycle.ACTIVE, observed_active=False)
        == AlertLifecycle.RESOLVED
    )
    assert (
        next_alert_lifecycle(
            AlertLifecycle.RESOLVED,
            observed_active=True,
            reopen_count=0,
        )
        == AlertLifecycle.REOPENED
    )
    assert (
        next_alert_lifecycle(
            AlertLifecycle.RESOLVED,
            observed_active=True,
            reopen_count=2,
            flapping_reopen_threshold=3,
        )
        == AlertLifecycle.FLAPPING
    )
