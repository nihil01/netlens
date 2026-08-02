"""Small process-local metric registry for Prometheus scraping."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

_values: defaultdict[str, float] = defaultdict(float)
_lock = Lock()


def increment(name: str, amount: float = 1) -> None:
    with _lock:
        _values[name] += amount


def set_gauge(name: str, value: float) -> None:
    with _lock:
        _values[name] = value


def value(name: str) -> float:
    with _lock:
        return _values[name]
