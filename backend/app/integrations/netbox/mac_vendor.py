from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WIRESHARK_MANUF_URL = "https://www.wireshark.org/assets/json/manuf.json"
DEFAULT_MANUF_CACHE_PATH = Path("/var/tmp/netlens/wireshark-manuf.json")


@dataclass(frozen=True)
class MacVendorInfo:
    mac_address: str
    oui: str | None
    vendor: str | None
    source: str


_MAC_HEX_RE = re.compile(r"^[0-9A-Fa-f]{12}$")
_OID_HEX_RE = re.compile(r"^[0-9A-Fa-f]{6,12}$")


def normalize_mac_address(value: str) -> str | None:
    compact = re.sub(r"[^0-9A-Fa-f]", "", value)
    if not _MAC_HEX_RE.match(compact):
        return None
    pairs = [compact[index : index + 2].upper() for index in range(0, 12, 2)]
    return ":".join(pairs)


def normalize_oid(value: str) -> str | None:
    compact = re.sub(r"[^0-9A-Fa-f]", "", value).lower()
    if not _OID_HEX_RE.match(compact):
        return None
    return compact


class WiresharkManufDataset:
    """Lazy cached lookup for Wireshark's JSON manufacturer dataset.

    The JSON shape is:
        {"created_at": "...", "data": {"001122": "Vendor", ...}}

    Wireshark includes both 24-bit OUIs and longer assignment keys. For a MAC address
    lookup we try the longest key first, then fall back to the base OUI.
    """

    def __init__(
        self,
        cache_path: str | Path | None = None,
        source_url: str = WIRESHARK_MANUF_URL,
        timeout_seconds: float = 10.0,
    ) -> None:
        configured_path = os.getenv("NETLENS_WIRESHARK_MANUF_CACHE")
        self.cache_path = Path(cache_path or configured_path or DEFAULT_MANUF_CACHE_PATH)
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self.created_at: str | None = None
        self._data: dict[str, str] | None = None

    def lookup_oid(self, oid: str) -> str | None:
        normalized = normalize_oid(oid)
        if normalized is None:
            return None
        data = self._load_data()
        return data.get(normalized.lower())

    def lookup_mac(self, normalized_mac: str) -> str | None:
        compact = re.sub(r"[^0-9A-Fa-f]", "", normalized_mac).lower()
        if not _MAC_HEX_RE.match(compact):
            return None
        data = self._load_data()
        for prefix_length in range(len(compact), 5, -1):
            vendor = data.get(compact[:prefix_length])
            if vendor:
                return vendor
        return None

    def _load_data(self) -> dict[str, str]:
        if self._data is not None:
            return self._data

        payload = self._read_cache()
        if payload is None:
            payload = self._download_dataset()
            if payload is not None:
                self._write_cache(payload)

        if payload is None:
            self._data = {}
            return self._data

        self.created_at = (
            payload.get("created_at") if isinstance(payload.get("created_at"), str) else None
        )
        raw_data = payload.get("data")
        if not isinstance(raw_data, dict):
            self._data = {}
            return self._data

        self._data = {
            str(key).lower(): str(value)
            for key, value in raw_data.items()
            if normalize_oid(str(key)) is not None and isinstance(value, str) and value
        }
        return self._data

    def _read_cache(self) -> dict[str, Any] | None:
        try:
            with self.cache_path.open("r", encoding="utf-8") as cache_file:
                payload = json.load(cache_file)
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _download_dataset(self) -> dict[str, Any] | None:
        try:
            with urllib.request.urlopen(self.source_url, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write_cache(self, payload: dict[str, Any]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.cache_path.with_suffix(f"{self.cache_path.suffix}.tmp")
            with tmp_path.open("w", encoding="utf-8") as cache_file:
                json.dump(payload, cache_file, ensure_ascii=False)
            tmp_path.replace(self.cache_path)
        except OSError:
            return


class MacVendorResolver:
    """Resolve MAC vendor for CAM/MAC-table rows via cached Wireshark manuf.json.

    Tests and offline use can still inject an OUI prefix mapping. That keeps current
    parser behavior stable while removing the dependency on the `manuf` Python package.
    """

    def __init__(
        self,
        dataset: WiresharkManufDataset | None = None,
        prefixes: dict[str, str] | None = None,
    ) -> None:
        self.dataset = dataset if dataset is not None else WiresharkManufDataset()
        self.prefixes = {self._normalize_oui(key): value for key, value in (prefixes or {}).items()}

    @classmethod
    def from_prefixes(cls, prefixes: dict[str, str]) -> MacVendorResolver:
        return cls(
            dataset=WiresharkManufDataset(cache_path=os.devnull, source_url=""),
            prefixes=prefixes,
        )

    def lookup(self, mac_address: str) -> MacVendorInfo:
        normalized = normalize_mac_address(mac_address)
        if normalized is None:
            return MacVendorInfo(
                mac_address=mac_address,
                oui=None,
                vendor=None,
                source="invalid",
            )

        oui = normalized[:8]
        vendor = self.prefixes.get(oui)
        if vendor:
            return MacVendorInfo(
                mac_address=normalized,
                oui=oui,
                vendor=vendor,
                source="prefix-dataset",
            )

        vendor = self.dataset.lookup_mac(normalized)
        return MacVendorInfo(
            mac_address=normalized,
            oui=oui,
            vendor=vendor,
            source="wireshark-manuf-json" if vendor else "unknown",
        )

    @staticmethod
    def _normalize_oui(value: str) -> str:
        normalized = (
            normalize_mac_address(f"{value}:00:00:00")
            if len(value) <= 8
            else normalize_mac_address(value)
        )
        if normalized is None:
            compact = re.sub(r"[^0-9A-Fa-f]", "", value).upper()
            return ":".join(
                compact[index : index + 2] for index in range(0, min(len(compact), 6), 2)
            )
        return normalized[:8]


def enrich_mac_table_entry(
    row: dict[str, object], resolver: MacVendorResolver | None = None
) -> dict[str, object]:
    """Attach normalized MAC vendor fields to one MAC/CAM table row.

    Parser-specific fields stay untouched. Only canonical MAC/vendor metadata is added,
    so Cisco/Juniper/Arista collectors can reuse the same enrichment step.
    """
    mac_value = row.get("mac_address") or row.get("mac")
    if not isinstance(mac_value, str):
        return {
            **row,
            "mac_vendor": None,
            "mac_oui": None,
            "mac_vendor_source": "missing",
        }

    info = (resolver or MacVendorResolver()).lookup(mac_value)
    return {
        **row,
        "mac_address": info.mac_address,
        "mac_vendor": info.vendor,
        "mac_oui": info.oui,
        "mac_vendor_source": info.source,
    }
