from __future__ import annotations

from app.integrations.netbox.mac_vendor import (
    MacVendorResolver,
    WiresharkManufDataset,
    enrich_mac_table_entry,
    normalize_mac_address,
)

from manuf import manuf


def test_check_manuf() -> None:
    p = manuf.MacParser(update=True)
    mac = "74:AD:98:72:00:00"

    print(p.get_manuf(mac), p.get_comment(mac))


def test_normalize_mac_address_accepts_common_formats() -> None:
    assert normalize_mac_address("0011.2233.4455") == "00:11:22:33:44:55"
    assert normalize_mac_address("00-11-22-33-44-55") == "00:11:22:33:44:55"
    assert normalize_mac_address("00:11:22:33:44:55") == "00:11:22:33:44:55"


def test_mac_vendor_resolver_uses_prefix_dataset() -> None:
    resolver = MacVendorResolver.from_prefixes({"00:11:22": "Cisco Systems"})

    result = resolver.lookup("0011.2233.4455")

    assert result.mac_address == "00:11:22:33:44:55"
    assert result.oui == "00:11:22"
    assert result.vendor == "Cisco Systems"
    assert result.source == "prefix-dataset"


def test_wireshark_dataset_reads_memory_json_by_oid() -> None:
    dataset = WiresharkManufDataset(
        source_url="memory://test-oid",
        initial_payload={
            "created_at": "2026-06-03T20:40:34Z",
            "data": {"001122": "Cisco Systems, Inc"},
        },
    )

    assert dataset.lookup_oid("00:11:22") == "Cisco Systems, Inc"
    assert dataset.lookup_oid("001122") == "Cisco Systems, Inc"
    assert dataset.created_at == "2026-06-03T20:40:34Z"


def test_wireshark_dataset_reuses_shared_memory_payload(monkeypatch) -> None:
    calls = 0

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            return b'{"created_at":"2026-06-03T20:40:34Z","data":{"001122":"Cisco Systems, Inc"}}'

    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse()

    source_url = "https://example.invalid/manuf.json"
    WiresharkManufDataset._shared_payloads.pop(source_url, None)
    monkeypatch.setattr("app.integrations.netbox.mac_vendor.urllib.request.urlopen", fake_urlopen)

    first_lookup = WiresharkManufDataset(source_url=source_url).lookup_oid("001122")
    second_lookup = WiresharkManufDataset(source_url=source_url).lookup_oid("00:11:22")

    assert first_lookup == "Cisco Systems, Inc"
    assert second_lookup == "Cisco Systems, Inc"
    assert calls == 1


def test_mac_vendor_resolver_uses_wireshark_dataset_without_manuf() -> None:
    resolver = MacVendorResolver(
        dataset=WiresharkManufDataset(
            source_url="memory://resolver-test",
            initial_payload={
                "created_at": "2026-06-03T20:40:34Z",
                "data": {"001122": "Cisco Systems, Inc"},
            },
        )
    )

    result = resolver.lookup("0011.2233.4455")

    assert result.oui == "00:11:22"
    assert result.vendor == "Cisco Systems, Inc"
    assert result.source == "wireshark-manuf-json"


def test_mac_vendor_resolver_handles_unknown_or_invalid_mac() -> None:
    resolver = MacVendorResolver.from_prefixes({})

    unknown = resolver.lookup("aa:bb:cc:dd:ee:ff")
    invalid = resolver.lookup("not-a-mac")

    assert unknown.vendor is None
    assert unknown.oui == "AA:BB:CC"
    assert invalid.vendor is None
    assert invalid.mac_address == "not-a-mac"
    assert invalid.source == "invalid"


def test_enrich_mac_table_entry_adds_vendor_without_losing_raw_fields() -> None:
    resolver = MacVendorResolver.from_prefixes({"00:11:22": "Cisco Systems"})
    row = {
        "vlan": 10,
        "mac_address": "0011.2233.4455",
        "interface": "Gi1/0/10",
        "type": "dynamic",
    }

    enriched = enrich_mac_table_entry(row, resolver)

    assert enriched["vlan"] == 10
    assert enriched["mac_address"] == "00:11:22:33:44:55"
    assert enriched["mac_vendor"] == "Cisco Systems"
    assert enriched["mac_oui"] == "00:11:22"
    assert enriched["mac_vendor_source"] == "prefix-dataset"
