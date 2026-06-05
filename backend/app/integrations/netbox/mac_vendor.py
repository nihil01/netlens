from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


class VendorLookupBackend(Protocol):
    def get_manuf(self, mac: str) -> str | None: ...


@dataclass(frozen=True)
class MacVendorInfo:
    mac_address: str
    oui: str | None
    vendor: str | None
    source: str


_MAC_HEX_RE = re.compile(r"^[0-9A-Fa-f]{12}$")


def normalize_mac_address(value: str) -> str | None:
    compact = re.sub(r"[^0-9A-Fa-f]", "", value)
    if not _MAC_HEX_RE.match(compact):
        return None
    pairs = [compact[index : index + 2].upper() for index in range(0, 12, 2)]
    return ":".join(pairs)


class MacVendorResolver:
    """Resolve MAC vendor for CAM/MAC-table rows.

    Default backend is the `manuf` library when installed. Tests and offline use can inject
    an OUI prefix mapping so the MAC-table parser remains independent from the dataset.
    """

    def __init__(
        self,
        backend: VendorLookupBackend | None = None,
        prefixes: dict[str, str] | None = None,
    ) -> None:
        self.backend = backend if backend is not None else self._create_manuf_backend()
        self.prefixes = {self._normalize_oui(key): value for key, value in (prefixes or {}).items()}

    @classmethod
    def from_prefixes(cls, prefixes: dict[str, str]) -> MacVendorResolver:
        return cls(backend=None, prefixes=prefixes)

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

        vendor = self.backend.get_manuf(normalized) if self.backend else None
        return MacVendorInfo(
            mac_address=normalized,
            oui=oui,
            vendor=vendor,
            source="manuf" if vendor else "unknown",
        )

    @staticmethod
    def _create_manuf_backend() -> VendorLookupBackend | None:
        try:
            from manuf import manuf
        except ImportError:
            return None
        return manuf.MacParser()

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
