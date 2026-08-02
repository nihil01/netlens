"""Pure FMC health-alert lifecycle rules."""

from enum import StrEnum


class AlertLifecycle(StrEnum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"
    FLAPPING = "FLAPPING"
    UNKNOWN = "UNKNOWN"


def next_alert_lifecycle(
    previous: AlertLifecycle | str | None,
    *,
    observed_active: bool,
    reopen_count: int = 0,
    flapping_reopen_threshold: int = 3,
) -> AlertLifecycle:
    try:
        previous_state = AlertLifecycle(previous) if previous else None
    except ValueError:
        previous_state = AlertLifecycle.UNKNOWN
    if not observed_active:
        return AlertLifecycle.RESOLVED if previous_state else AlertLifecycle.UNKNOWN
    if previous_state is None:
        return AlertLifecycle.NEW
    if previous_state == AlertLifecycle.RESOLVED:
        if reopen_count + 1 >= flapping_reopen_threshold:
            return AlertLifecycle.FLAPPING
        return AlertLifecycle.REOPENED
    if previous_state == AlertLifecycle.UNKNOWN:
        return AlertLifecycle.ACTIVE
    if previous_state == AlertLifecycle.FLAPPING:
        return AlertLifecycle.FLAPPING
    return AlertLifecycle.ACTIVE
