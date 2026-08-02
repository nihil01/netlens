"""CIDR notation support for OpenSearch IP queries.

Converts CIDR notation (e.g. 10.0.0.0/8) to OpenSearch wildcard or range
queries that match all IPs within the subnet.
"""

from __future__ import annotations

import ipaddress
from typing import Any


def is_cidr(value: str) -> bool:
    """Check if a string looks like CIDR notation."""
    return "/" in value


def validate_cidr(value: str) -> bool:
    """Validate CIDR notation. Returns True if valid."""
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False


def cidr_to_wildcard(cidr: str) -> str:
    """Convert CIDR to an OpenSearch wildcard pattern.

    Works efficiently for /8, /16, /24 masks.
    Example: 10.0.0.0/8 → "10.*.*.*"
    """
    network = ipaddress.ip_network(cidr, strict=False)
    prefix_len = network.prefixlen

    if prefix_len == 8:
        first_octet = str(network.network_address).split(".")[0]
        return f"{first_octet}.*.*.*"
    elif prefix_len == 16:
        parts = str(network.network_address).split(".")
        return f"{parts[0]}.{parts[1]}.*.*"
    elif prefix_len == 24:
        parts = str(network.network_address).split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.*"
    else:
        # For non-standard masks, fall back to range query
        return ""


def cidr_to_range(cidr: str) -> tuple[str, str]:
    """Convert CIDR to (gte, lte) range boundaries."""
    network = ipaddress.ip_network(cidr, strict=False)
    first_ip = str(network.network_address)
    last_ip = str(network.broadcast_address)
    return first_ip, last_ip


def cidr_to_opensearch_filter(
    cidr: str,
    fields: list[str],
) -> dict[str, Any]:
    """Convert CIDR to an OpenSearch filter clause.

    For /8, /16, /24 → uses wildcard query.
    For other prefix lengths → uses ip_range query.
    """
    prefix_len = ipaddress.ip_network(cidr, strict=False).prefixlen

    if prefix_len in (8, 16, 24):
        wildcard = cidr_to_wildcard(cidr)
        return {
            "bool": {
                "should": [{"wildcard": {field: wildcard}} for field in fields],
                "minimum_should_match": 1,
            }
        }
    else:
        gte, lte = cidr_to_range(cidr)
        return {
            "bool": {
                "should": [{"range": {field: {"gte": gte, "lte": lte}}} for field in fields],
                "minimum_should_match": 1,
            }
        }
