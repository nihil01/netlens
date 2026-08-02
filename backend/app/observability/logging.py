"""Structured JSON logging with conservative inline secret masking."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

_SECRET = re.compile(
    r"(?i)\b(authorization|cookie|password|passwd|secret|token)\b(\s*[:=]\s*)([^\s,;]+)"
)
_EXTRA_FIELDS = (
    "component",
    "collection_run_id",
    "device_id",
    "endpoint",
    "http_status",
    "duration_ms",
    "error_class",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "message": _SECRET.sub(r"\1\2***", record.getMessage()),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["error_class"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
