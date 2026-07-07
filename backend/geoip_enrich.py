#!/usr/bin/env python3
"""
GeoLite2 ASN IP Enrichment Script

Standalone script for IP-to-ASN resolution using MaxMind GeoLite2 database.
Automatically downloads the database if not present.

Usage:
    # Single IP
    python geoip_enrich.py 157.240.17.35

    # Multiple IPs
    python geoip_enrich.py 8.8.8.8 1.1.1.1 157.240.17.35

    # From file (one IP per line)
    python geoip_enrich.py --file ips.txt

    # JSON output
    python geoip_enrich.py --json 8.8.8.8 1.1.1.1

Requirements:
    pip install geoip2
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import sys
import tarfile
import threading
import urllib.request
from typing import Any

try:
    import geoip2.database
    import geoip2.errors
except ImportError:
    print("Error: geoip2 not installed. Run: pip install geoip2")
    sys.exit(1)


# --- Configuration ---
_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geoip_data")
_DB_FILENAME = "GeoLite2-ASN.mmdb"
_DB_PATH = os.path.join(_DB_DIR, _DB_FILENAME)

_MAXMIND_LICENSE_KEY = os.getenv("MAXMIND_LICENSE_KEY", "")
_DOWNLOAD_URL = (
    "https://download.maxmind.com/app/geoip_download"
    "?edition_id=GeoLite2-ASN&license_key={key}&suffix=tar.gz"
)

# --- Vendor normalization ---
_VENDOR_MAP: dict[str, tuple[str, str]] = {
    "meta": ("Meta", "social_media"),
    "facebook": ("Meta", "social_media"),
    "instagram": ("Meta", "social_media"),
    "whatsapp": ("Meta", "social_media"),
    "google": ("Google", "cloud_provider"),
    "youtube": ("Google", "social_media"),
    "cloudflare": ("Cloudflare", "cdn_security"),
    "telegram": ("Telegram", "messaging"),
    "amazon": ("Amazon AWS", "cloud_provider"),
    "aws": ("Amazon AWS", "cloud_provider"),
    "microsoft": ("Microsoft", "cloud_provider"),
    "azure": ("Microsoft", "cloud_provider"),
    "akamai": ("Akamai", "cdn"),
    "fastly": ("Fastly", "cdn"),
    "cloudfront": ("Amazon AWS", "cdn"),
    "github": ("GitHub", "cloud_provider"),
    "netflix": ("Netflix", "streaming"),
    "apple": ("Apple", "cloud_provider"),
    "oracle": ("Oracle", "cloud_provider"),
    "digitalocean": ("DigitalOcean", "cloud_provider"),
    "hetzner": ("Hetzner", "cloud_provider"),
    "ovh": ("OVH", "cloud_provider"),
    "verizon": ("Verizon", "telecom"),
    "att": ("AT&T", "telecom"),
    "comcast": ("Comcast", "telecom"),
    "alibaba": ("Alibaba Cloud", "cloud_provider"),
    "tencent": ("Tencent Cloud", "cloud_provider"),
}

_lock = threading.Lock()
_reader: geoip2.database.Reader | None = None


def _ensure_db() -> str:
    """Download GeoLite2 ASN database if not present."""
    if os.path.exists(_DB_PATH):
        return _DB_PATH

    if not _MAXMIND_LICENSE_KEY:
        print(f"Error: GeoLite2 ASN database not found at {_DB_PATH}")
        print("Set MAXMIND_LICENSE_KEY environment variable or download manually:")
        print("  1. Sign up at https://www.maxmind.com/en/geolite2/signup")
        print("  2. Download GeoLite2 ASN")
        print(f"  3. Place .mmdb file at {_DB_PATH}")
        sys.exit(1)

    os.makedirs(_DB_DIR, exist_ok=True)
    url = _DOWNLOAD_URL.format(key=_MAXMIND_LICENSE_KEY)
    tar_path = os.path.join(_DB_DIR, "geolite2-asn.tar.gz")

    print("Downloading GeoLite2 ASN database...")
    urllib.request.urlretrieve(url, tar_path)

    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.endswith(".mmdb"):
                member.name = _DB_FILENAME
                tar.extract(member, _DB_DIR)
                break

    os.remove(tar_path)
    print(f"Database saved to {_DB_PATH}")
    return _DB_PATH


def _get_reader() -> geoip2.database.Reader:
    """Get or create the GeoIP2 reader (thread-safe singleton)."""
    global _reader
    if _reader is not None:
        return _reader

    with _lock:
        if _reader is not None:
            return _reader
        db_path = _ensure_db()
        _reader = geoip2.database.Reader(db_path)
        return _reader


def _normalize_vendor(org: str) -> tuple[str, str]:
    """Normalize ASN organization to vendor name and category."""
    if not org:
        return ("Unknown", "unknown")

    org_lower = org.lower()
    for keyword, (vendor, category) in _VENDOR_MAP.items():
        if keyword in org_lower:
            return (vendor, category)

    return (org, "unknown")


def enrich_ip(ip: str) -> dict[str, Any]:
    """
    Enrich a single IP address with ASN information.

    Args:
        ip: IP address string

    Returns:
        dict with keys: ip, scope, asn, asn_org, vendor, category
    """
    result: dict[str, Any] = {
        "ip": ip,
        "scope": "unknown",
        "asn": None,
        "asn_org": None,
        "vendor": "Unknown",
        "category": "unknown",
    }

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        result["scope"] = "invalid"
        return result

    if addr.is_loopback:
        result["scope"] = "loopback"
        return result

    if addr.is_private:
        result["scope"] = "private"
        return result

    if addr.is_multicast or addr.is_reserved or addr.is_link_local:
        result["scope"] = "reserved"
        return result

    result["scope"] = "public"

    try:
        reader = _get_reader()
        response = reader.asn(ip)
        result["asn"] = response.autonomous_system_number
        result["asn_org"] = response.autonomous_system_organization or None

        if response.autonomous_system_organization:
            vendor, category = _normalize_vendor(response.autonomous_system_organization)
            result["vendor"] = vendor
            result["category"] = category

    except (geoip2.errors.AddressNotFoundError, ValueError):
        pass
    except Exception as exc:
        logging.debug("GeoIP2 lookup failed for %s: %s", ip, exc)

    return result


def enrich_ips(ips: list[str]) -> list[dict[str, Any]]:
    """
    Enrich multiple IP addresses with ASN information.
    Uses in-memory cache for repeated IPs.

    Args:
        ips: List of IP address strings

    Returns:
        List of enrichment dicts
    """
    cache: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for ip in ips:
        if ip not in cache:
            cache[ip] = enrich_ip(ip)
        results.append(cache[ip])

    return results


def close() -> None:
    """Close the GeoIP2 reader."""
    global _reader
    with _lock:
        if _reader is not None:
            _reader.close()
            _reader = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IP-to-ASN enrichment using MaxMind GeoLite2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 157.240.17.35
  %(prog)s 8.8.8.8 1.1.1.1 157.240.17.35
  %(prog)s --file ips.txt
  %(prog)s --json 8.8.8.8 1.1.1.1
        """,
    )
    parser.add_argument("ips", nargs="*", help="IP addresses to enrich")
    parser.add_argument("--file", "-f", help="File with IPs (one per line)")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    ips: list[str] = []

    if args.file:
        with open(args.file) as f:
            ips.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))

    if args.ips:
        ips.extend(args.ips)

    if not ips:
        parser.print_help()
        sys.exit(1)

    results = enrich_ips(ips)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            scope_icon = {"public": "🌍", "private": "🔒", "invalid": "❌", "loopback": "🔄", "reserved": "⚠️"}.get(r["scope"], "❓")
            print(f"{scope_icon} {r['ip']}")
            print(f"   Scope: {r['scope']}")
            if r["asn"]:
                print(f"   ASN: AS{r['asn']}")
            if r["asn_org"]:
                print(f"   Org: {r['asn_org']}")
            print(f"   Vendor: {r['vendor']}")
            print(f"   Category: {r['category']}")
            print()

    close()


if __name__ == "__main__":
    main()
