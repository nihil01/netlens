"""
GeoLite2 ASN + Country IP Enrichment Module

Provides local IP-to-ASN and IP-to-Country resolution using MaxMind GeoLite2 databases.

Usage:
    from app.integrations.geoip.asn_enricher import enrich_ip, enrich_ips

    result = enrich_ip("157.240.17.35")
    # {"ip": "157.240.17.35", "scope": "public", "asn": 32934, "country": "US", ...}

    results = enrich_ips(["8.8.8.8", "10.0.0.1", "157.240.17.35"])
"""

from __future__ import annotations

import ipaddress
import logging
import os
import threading
from typing import Any

import geoip2.database
import geoip2.errors

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "geoip_data"))
_ASN_DB = os.path.join(_DATA_DIR, "GeoLite2-ASN.mmdb")
_COUNTRY_DB = os.path.join(_DATA_DIR, "GeoLite2-Country.mmdb")

_lock = threading.Lock()
_asn_reader: geoip2.database.Reader | None = None
_country_reader: geoip2.database.Reader | None = None


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
    "yunjiasu": ("Baidu", "cdn"),
    "alibaba": ("Alibaba Cloud", "cloud_provider"),
    "tencent": ("Tencent Cloud", "cloud_provider"),
}


def _get_readers() -> tuple[geoip2.database.Reader, geoip2.database.Reader]:
    """Get or create GeoIP2 readers (thread-safe singleton)."""
    global _asn_reader, _country_reader

    with _lock:
        if _asn_reader is None and os.path.exists(_ASN_DB):
            _asn_reader = geoip2.database.Reader(_ASN_DB)
        if _country_reader is None and os.path.exists(_COUNTRY_DB):
            _country_reader = geoip2.database.Reader(_COUNTRY_DB)

    if _asn_reader is None:
        raise FileNotFoundError(f"ASN database not found: {_ASN_DB}")
    if _country_reader is None:
        raise FileNotFoundError(f"Country database not found: {_COUNTRY_DB}")

    return _asn_reader, _country_reader


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
    Enrich a single IP address with ASN + Country information.

    Returns:
        dict with keys: ip, scope, asn, asn_org, vendor, category, country, country_name
    """
    result: dict[str, Any] = {
        "ip": ip,
        "scope": "unknown",
        "asn": None,
        "asn_org": None,
        "vendor": "Unknown",
        "category": "unknown",
        "country": None,
        "country_name": None,
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
        asn_reader, country_reader = _get_readers()

        # ASN lookup
        try:
            asn_resp = asn_reader.asn(ip)
            result["asn"] = asn_resp.autonomous_system_number
            result["asn_org"] = asn_resp.autonomous_system_organization or None
            if asn_resp.autonomous_system_organization:
                vendor, category = _normalize_vendor(asn_resp.autonomous_system_organization)
                result["vendor"] = vendor
                result["category"] = category
        except (geoip2.errors.AddressNotFoundError, ValueError):
            pass

        # Country lookup
        try:
            country_resp = country_reader.country(ip)
            result["country"] = country_resp.country.iso_code or None
            result["country_name"] = country_resp.country.name or None
        except (geoip2.errors.AddressNotFoundError, ValueError):
            pass

    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("GeoIP2 lookup failed for %s: %s", ip, exc)

    return result


def enrich_ips(ips: list[str]) -> list[dict[str, Any]]:
    """Enrich multiple IPs with ASN + Country. Uses in-memory cache."""
    cache: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for ip in ips:
        if ip not in cache:
            cache[ip] = enrich_ip(ip)
        results.append(cache[ip])

    return results


def close() -> None:
    """Close GeoIP2 readers. Call on application shutdown."""
    global _asn_reader, _country_reader
    with _lock:
        if _asn_reader is not None:
            _asn_reader.close()
            _asn_reader = None
        if _country_reader is not None:
            _country_reader.close()
            _country_reader = None
