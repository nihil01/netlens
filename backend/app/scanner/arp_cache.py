from __future__ import annotations

import re
from threading import RLock
from typing import Any

_LOCK = RLock()
_ARP_BY_IP: dict[str, dict[str, Any]] = {}


def normalize_mac(raw_mac: str | None) -> str | None:
    if not raw_mac:
        return None
    clean = re.sub(r"[^0-9a-fA-F]", "", str(raw_mac)).upper()
    if len(clean) != 12:
        return None
    return ":".join(clean[index : index + 2] for index in range(0, 12, 2))


def update_arp_entries(entries: list[dict[str, Any]], *, source: str | None = None) -> None:
    normalized: dict[str, dict[str, Any]] = {}
    for row in entries:
        ip = str(row.get("address") or row.get("ip") or row.get("ip_address") or "").strip()
        mac = normalize_mac(
            row.get("mac")
            or row.get("mac_address")
            or row.get("hardware_addr")
            or row.get("hw_address")
        )
        if not ip or not mac:
            continue
        normalized[ip] = {
            "ip": ip,
            "mac_address": mac,
            "interface": row.get("interface") or row.get("port"),
            "age": row.get("age"),
            "source": source,
            "raw": row,
        }

    if not normalized:
        return

    with _LOCK:
        _ARP_BY_IP.update(normalized)


def lookup_arp_mac(ip: str) -> str | None:
    with _LOCK:
        entry = _ARP_BY_IP.get(ip)
        return str(entry["mac_address"]) if entry else None


def snapshot() -> dict[str, dict[str, Any]]:
    with _LOCK:
        return dict(_ARP_BY_IP)
