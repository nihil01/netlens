from typing import Any

import httpx

from app.core.config import Settings


def create_opensearch_client(settings: Settings) -> httpx.AsyncClient:
    """Create an async HTTP client configured for OpenSearch."""
    auth = None

    if settings.opensearch_username and settings.opensearch_password:
        auth = (
            settings.opensearch_username,
            settings.opensearch_password,
        )

    return httpx.AsyncClient(
        base_url=str(settings.opensearch_url).rstrip("/"),
        auth=auth,
        verify=settings.opensearch_verify_ssl,
        timeout=settings.opensearch_timeout_seconds,
    )


def first_value(source: dict[str, Any], fields: list[str]) -> Any:
    """Return the first non-empty value from *fields* in *source*."""
    for field in fields:
        value = get_value(source, field)

        if value not in (None, "", [], {}):
            return value

    return None


def get_value(source: dict[str, Any], dotted_path: str) -> Any:
    """Walk a dotted path inside a nested dict and return the leaf value."""
    current: Any = source

    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None

        current = current.get(part)

        if current is None:
            return None

    return current


def sum_int_values(source: dict[str, Any], fields: list[str]) -> int | None:
    """Sum integer values found in *fields* of *source*."""
    total = 0
    found = False

    for field in fields:
        value = as_int(get_value(source, field))

        if value is not None:
            total += value
            found = True

    return total if found else None


def as_str(value: Any) -> str | None:
    """Coerce *value* to a string representation, or ``None``."""
    if value in (None, "", [], {}):
        return None

    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item not in (None, ""))

    return str(value)


def as_int(value: Any) -> int | None:
    """Coerce *value* to an int, or ``None``."""
    if value in (None, "", [], {}):
        return None

    if isinstance(value, list):
        value = value[0] if value else None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None
