"""Timezone utilities for Baku (GMT+4)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

BAKU_TZ = timezone(timedelta(hours=4))


def to_baku(dt: datetime | str | None) -> str:
    """Convert datetime to Baku time string (YYYY-MM-DD HH:MM:SS)."""
    if dt is None:
        return "—"

    if isinstance(dt, str):
        # Parse ISO string
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return dt[:19] if len(dt) >= 19 else dt

    # If naive, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    baku_dt = dt.astimezone(BAKU_TZ)
    return baku_dt.strftime("%Y-%m-%d %H:%M:%S")


def now_baku() -> str:
    """Get current Baku time string."""
    return datetime.now(BAKU_TZ).strftime("%Y-%m-%d %H:%M:%S")


def baku_timestamp() -> str:
    """Get current Baku time as ISO string with +04:00."""
    return datetime.now(BAKU_TZ).isoformat()
