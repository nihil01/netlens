from app.integrations.netbox.mac_vendor import (
    MacVendorResolver,
    enrich_mac_table_entry,
    normalize_mac_address,
)


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
