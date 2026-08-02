"""Pure VPN state-transition and availability analytics."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from statistics import mean


class TunnelState(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"
    DEGRADED = "DEGRADED"
    FLAPPING = "FLAPPING"


@dataclass(frozen=True)
class TunnelTransition:
    previous_status: TunnelState
    new_status: TunnelState
    changed_at: datetime
    duration_in_previous_state_seconds: int | None = None


@dataclass(frozen=True)
class TunnelServiceMetrics:
    availability_percent: float | None
    up_seconds: int
    down_seconds: int
    unknown_seconds: int
    transition_count: int
    longest_outage_seconds: int
    mtbf_seconds: float | None
    mttr_seconds: float | None
    flapping: bool


def normalize_tunnel_state(value: str | None) -> TunnelState:
    normalized = str(value or "").strip().upper()
    return {
        "UP": TunnelState.UP,
        "TUNNEL_UP": TunnelState.UP,
        "ACTIVE": TunnelState.UP,
        "DOWN": TunnelState.DOWN,
        "TUNNEL_DOWN": TunnelState.DOWN,
        "INACTIVE": TunnelState.DOWN,
        "DEGRADED": TunnelState.DEGRADED,
        "FLAPPING": TunnelState.FLAPPING,
    }.get(normalized, TunnelState.UNKNOWN)


def detect_transition(
    previous_status: str | TunnelState | None,
    observed_status: str | TunnelState | None,
    *,
    changed_at: datetime,
    previous_changed_at: datetime | None = None,
) -> TunnelTransition | None:
    previous = normalize_tunnel_state(str(previous_status) if previous_status else None)
    observed = normalize_tunnel_state(str(observed_status) if observed_status else None)
    if previous == observed:
        return None
    duration = None
    if previous_changed_at is not None:
        duration = max(0, int((changed_at - previous_changed_at).total_seconds()))
    return TunnelTransition(previous, observed, changed_at, duration)


def is_flapping(
    transitions: Iterable[TunnelTransition],
    *,
    threshold: int = 3,
    window_seconds: int = 900,
    at: datetime | None = None,
) -> bool:
    if threshold <= 0:
        return True
    reference = _aware(at or datetime.now(UTC))
    window_start = reference - timedelta(seconds=max(1, window_seconds))
    recent = [
        transition
        for transition in transitions
        if window_start <= _aware(transition.changed_at) <= reference
    ]
    return len(recent) >= threshold


def calculate_service_metrics(
    transitions: Iterable[TunnelTransition],
    *,
    period_start: datetime,
    period_end: datetime,
    initial_status: str | TunnelState = TunnelState.UNKNOWN,
    flap_threshold: int = 3,
    flap_window_seconds: int = 900,
) -> TunnelServiceMetrics:
    start = _aware(period_start)
    end = _aware(period_end)
    if end < start:
        raise ValueError("period_end must not be before period_start")
    ordered = sorted(transitions, key=lambda item: _aware(item.changed_at))
    state = normalize_tunnel_state(str(initial_status))
    cursor = start
    durations = {TunnelState.UP: 0, TunnelState.DOWN: 0, TunnelState.UNKNOWN: 0}
    completed_up_segments: list[int] = []
    completed_down_segments: list[int] = []
    all_down_segments: list[int] = []

    for transition in ordered:
        changed_at = _aware(transition.changed_at)
        if changed_at <= start:
            state = transition.new_status
            continue
        if changed_at > end:
            break
        segment = max(0, int((changed_at - cursor).total_seconds()))
        bucket = _bucket(state)
        durations[bucket] += segment
        if state == TunnelState.UP:
            completed_up_segments.append(segment)
        elif state == TunnelState.DOWN:
            completed_down_segments.append(segment)
            all_down_segments.append(segment)
        state = transition.new_status
        cursor = changed_at

    final_segment = max(0, int((end - cursor).total_seconds()))
    bucket = _bucket(state)
    durations[bucket] += final_segment
    if state == TunnelState.DOWN:
        all_down_segments.append(final_segment)

    known_seconds = durations[TunnelState.UP] + durations[TunnelState.DOWN]
    availability = (
        round(durations[TunnelState.UP] * 100 / known_seconds, 5) if known_seconds else None
    )
    transitions_in_period = [item for item in ordered if start < _aware(item.changed_at) <= end]
    return TunnelServiceMetrics(
        availability_percent=availability,
        up_seconds=durations[TunnelState.UP],
        down_seconds=durations[TunnelState.DOWN],
        unknown_seconds=durations[TunnelState.UNKNOWN],
        transition_count=len(transitions_in_period),
        longest_outage_seconds=max(all_down_segments, default=0),
        mtbf_seconds=mean(completed_up_segments) if completed_up_segments else None,
        mttr_seconds=mean(completed_down_segments) if completed_down_segments else None,
        flapping=is_flapping(
            transitions_in_period,
            threshold=flap_threshold,
            window_seconds=flap_window_seconds,
            at=end,
        ),
    )


def _bucket(state: TunnelState) -> TunnelState:
    if state == TunnelState.UP:
        return TunnelState.UP
    if state == TunnelState.DOWN:
        return TunnelState.DOWN
    return TunnelState.UNKNOWN


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
