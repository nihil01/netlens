from __future__ import annotations

import ipaddress
import re
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.integrations.opensearch.client import (
    as_int,
    as_str,
    create_opensearch_client,
    first_value,
    get_value,
    sum_int_values,
)
from app.integrations.opensearch.mappings import (
    OpenSearchSourceMapping,
    build_source_mappings,
)
from app.integrations.opensearch.query import build_ip_logs_query
from app.ip_intelligence.schemas import (
    ActivityCounterparty,
    ActivitySummary,
    IntegrationStatus,
    UnifiedActivityEvent,
)


class OpenSearchActivityService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._internal_networks = [
            ipaddress.ip_network(cidr)
            for cidr in settings.internal_cidrs
        ]

    @classmethod
    def from_settings(cls) -> OpenSearchActivityService:
        return cls(get_settings())

    # ------------------------------------------------------------------
    # Client helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        return create_opensearch_client(self.settings)

    # ------------------------------------------------------------------
    # Source mappings
    # ------------------------------------------------------------------

    def _source_mappings(self) -> list[OpenSearchSourceMapping]:
        return build_source_mappings(self.settings)

    # ------------------------------------------------------------------
    # Query builder (delegated)
    # ------------------------------------------------------------------

    @staticmethod
    def build_ip_logs_query(
        mapping: OpenSearchSourceMapping,
        ip: str,
        window: str = "24h",
        start: str | None = None,
        end: str | None = None,
        size: int = 100,
        src_ip: str | None = None,
        dst_ip: str | None = None,
        dst_port: int | None = None,
    ) -> dict[str, Any]:
        return build_ip_logs_query(
            mapping=mapping,
            ip=ip,
            window=window,
            start=start,
            end=end,
            size=size,
            src_ip=src_ip,
            dst_ip=dst_ip,
            dst_port=dst_port,
        )

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    def _extract_user_from_event(self, event: UnifiedActivityEvent) -> str | None:
        if event.user:
            return event.user

        message = ""
        if isinstance(event.raw, dict):
            message = str(event.raw.get("message") or "")

        patterns = [
            r"User <([^>]+)>",
            r"\(LOCAL\\([^)]+)\)",
            r"\(([^)]+)\)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)

        return None

    def _counter_to_ports(
            self,
            counter: dict[int, int],
    ) -> list[ActivityCounterparty]:
        items = sorted(counter.items(), key=lambda item: item[1], reverse=True)

        return [
            ActivityCounterparty(
                ip="",
                port=port,
                service=None,
                count=count,
            )
            for port, count in items
        ]

    def _counter_to_domains(
            self,
            counter: dict[str, int],
    ) -> list[ActivityCounterparty]:
        items = sorted(counter.items(), key=lambda item: item[1], reverse=True)

        return [
            ActivityCounterparty(
                ip=domain,
                port=None,
                service=None,
                count=count,
            )
            for domain, count in items
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_ip_logs(
            self,
            ip: str,
            window: str = "24h",
            start: str | None = None,
            end: str | None = None,
            size_per_source: int = 100,
            src_ip: str | None = None,
            dst_ip: str | None = None,
            dst_port: int | None = None,
    ) -> dict[str, Any]:
        mappings = self._source_mappings()
        logs: list[dict[str, Any]] = []

        async with self._client() as client:
            for mapping in mappings:
                body = self.build_ip_logs_query(
                    mapping=mapping,
                    ip=ip,
                    window=window,
                    start=start,
                    end=end,
                    size=size_per_source,
                    src_ip=src_ip,
                    dst_ip=dst_ip,
                    dst_port=dst_port,
                )

                try:
                    response = await client.post(
                        f"/{mapping.index_pattern}/_search",
                        json=body,
                    )
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                except httpx.HTTPStatusError:
                    continue

                data = response.json()
                events = self._map_hits(
                    data=data,
                    mapping=mapping,
                    ip=ip,
                )

                hits = data.get("hits", {}).get("hits", [])

                for hit, event in zip(hits, events):
                    logs.append({
                        "source_name": event.source_name,
                        "index": event.index,
                        "id": hit.get("_id"),
                        "timestamp": event.timestamp,
                        "source_ip": event.source_ip,
                        "source_port": event.source_port,
                        "destination_ip": event.destination_ip,
                        "destination_port": event.destination_port,
                        "protocol": event.protocol,
                        "action": event.action,
                        "application": event.application,
                        "rule": event.rule,
                        "policy": event.policy,
                        "user": event.user,
                        "domain": event.domain,
                        "url": event.url,
                        "bytes": event.bytes,
                        "packets": event.packets,
                        "direction": event.direction,
                        "is_source_ip": event.is_source_ip,
                        "is_destination_ip": event.is_destination_ip,
                        "raw": event.raw,
                    })

        logs.sort(key=lambda item: item.get("timestamp") or "", reverse=True)

        return {
            "status": {"status": "ok"},
            "ip": ip,
            "window": window if not start else f"{start} - {end or 'now'}",
            "total": len(logs),
            "logs": logs,
        }

    async def summarize_ip(
        self,
        ip: str,
        window: str = "24h",
        start: str | None = None,
        end: str | None = None,
        size_per_source: int = 100,
        src_ip: str | None = None,
        dst_ip: str | None = None,
        dst_port: int | None = None,
    ) -> ActivitySummary:
        if not self.settings.opensearch_url:
            return ActivitySummary(
                window=window,
                status=IntegrationStatus(
                    status="not_configured",
                    message="OPENSEARCH_URL is required",
                ),
            )

        try:
            mappings = self._source_mappings()

            async with self._client() as client:
                events: list[UnifiedActivityEvent] = []

                for mapping in mappings:
                    body = self.build_ip_logs_query(
                        mapping=mapping,
                        ip=ip,
                        window=window,
                        start=start,
                        end=end,
                        size=size_per_source,
                        src_ip=src_ip,
                        dst_ip=dst_ip,
                        dst_port=dst_port,
                    )

                    try:
                        response = await client.post(
                            f"/{mapping.index_pattern}/_search",
                            json=body,
                        )
                        if response.status_code == 404:
                            continue
                        response.raise_for_status()
                    except httpx.HTTPStatusError:
                        continue

                    source_events = self._map_hits(
                        data=response.json(),
                        mapping=mapping,
                        ip=ip,
                    )

                    events.extend(source_events)

                events.sort(
                    key=lambda item: item.timestamp or "",
                    reverse=True,
                )

                return self._build_summary_from_events(
                    ip=ip,
                    events=events,
                    window=window if not start else f"{start} - {end or 'now'}",
                )

        except httpx.HTTPError as exc:
            return ActivitySummary(
                window=window,
                status=IntegrationStatus(
                    status="error",
                    message=f"OpenSearch HTTP error: {exc}",
                ),
            )
        except Exception as exc:
            return ActivitySummary(
                window=window,
                status=IntegrationStatus(
                    status="error",
                    message=f"OpenSearch mapping error: {exc}",
                ),
            )

    # ------------------------------------------------------------------
    # Domain / Application aggregation
    # ------------------------------------------------------------------

    async def aggregate_domains_by_ip(
        self,
        ip: str,
        start: str | None = None,
        end: str | None = None,
        size: int = 1000,
    ) -> dict[str, Any]:
        """Aggregate domains and applications for an IP using painless scripts."""
        from app.integrations.opensearch.mappings import (
            APPLICATION_EXTRACTION_SCRIPT,
            DOMAIN_EXTRACTION_SCRIPT,
        )

        # Build time range
        if start:
            time_range = {"range": {"@timestamp": {"gte": start, "lte": end or "now"}}}
        else:
            time_range = {"range": {"@timestamp": {"gte": "now-7d", "lte": "now"}}}

        # Build IP should clause across checkpoint + fmc_estreamer fields
        ip_should = [
            {"term": {"src": ip}},
            {"term": {"initiator_ip": ip}},
            {"term": {"original_initiator_ip": ip}},
            {"term": {"client_ip": ip}},
            {"term": {"endpoint_ip": ip}},
            {"term": {"xlatesrc": ip}},
            {"term": {"proxy_src_ip": ip}},
            {"term": {"destination.ip": ip}},
            {"term": {"responder_ip": ip}},
            {"term": {"extra_fields.NAT_InitiatorIP": ip}},
            {"term": {"extra_fields.NAT_ResponderIP": ip}},
            {"term": {"source.ip": ip}},
        ]

        body = {
            "size": 0,
            "track_total_hits": False,
            "query": {
                "bool": {
                    "filter": [time_range],
                    "should": ip_should,
                    "minimum_should_match": 1,
                }
            },
            "aggs": {
                "activity": {
                    "composite": {
                        "size": size,
                        "sources": [
                            {
                                "domain": {
                                    "terms": {
                                        "script": {
                                            "lang": "painless",
                                            "source": DOMAIN_EXTRACTION_SCRIPT,
                                        }
                                    }
                                }
                            },
                            {
                                "application": {
                                    "terms": {
                                        "script": {
                                            "lang": "painless",
                                            "source": APPLICATION_EXTRACTION_SCRIPT,
                                        }
                                    }
                                }
                            },
                        ],
                    },
                    "aggs": {
                        "first_seen": {"min": {"field": "@timestamp"}},
                        "last_seen": {"max": {"field": "@timestamp"}},
                    },
                }
            },
        }

        # Search across checkpoint + fmc-estreamer indices
        index_patterns = [
            self.settings.opensearch_checkpoint_index_pattern,
            self.settings.opensearch_fmc_estreamer_index_pattern,
        ]

        combined_buckets: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()

        async with self._client() as client:
            for pattern in index_patterns:
                try:
                    response = await client.post(f"/{pattern}/_search", json=body)
                    response.raise_for_status()
                    data = response.json()

                    for bucket in data.get("aggregations", {}).get("activity", {}).get("buckets", []):
                        key = (
                            bucket.get("key", {}).get("domain", ""),
                            bucket.get("key", {}).get("application", ""),
                        )
                        if key not in seen_keys:
                            seen_keys.add(key)
                            combined_buckets.append(bucket)
                except Exception:
                    continue

        # Sort by doc_count descending
        combined_buckets.sort(key=lambda b: b.get("doc_count", 0), reverse=True)

        return {
            "ip": ip,
            "total_buckets": len(combined_buckets),
            "buckets": combined_buckets[:size],
        }

    # ------------------------------------------------------------------
    # Full aggregation (domains + IPs + ports + protocols + actions)
    # ------------------------------------------------------------------

    async def aggregate_full_by_ip(
        self,
        ip: str,
        start: str | None = None,
        end: str | None = None,
        size: int = 500,
        src_ip: str | None = None,
        dst_ip: str | None = None,
        dst_port: int | None = None,
    ) -> dict[str, Any]:
        """Full aggregation: domains, top IPs, top ports, protocols, actions, users."""
        from app.integrations.opensearch.mappings import (
            APPLICATION_EXTRACTION_SCRIPT,
            DOMAIN_EXTRACTION_SCRIPT,
        )

        if start:
            time_range = {"range": {"@timestamp": {"gte": start, "lte": end or "now"}}}
        else:
            time_range = {"range": {"@timestamp": {"gte": "now-7d", "lte": "now"}}}

        ip_should = [
            {"term": {"src": ip}},
            {"term": {"initiator_ip": ip}},
            {"term": {"original_initiator_ip": ip}},
            {"term": {"client_ip": ip}},
            {"term": {"endpoint_ip": ip}},
            {"term": {"xlatesrc": ip}},
            {"term": {"proxy_src_ip": ip}},
            {"term": {"destination.ip": ip}},
            {"term": {"responder_ip": ip}},
            {"term": {"extra_fields.NAT_InitiatorIP": ip}},
            {"term": {"extra_fields.NAT_ResponderIP": ip}},
            {"term": {"source.ip": ip}},
        ]

        # Build additional filters
        extra_filters: list[dict[str, Any]] = []
        if src_ip:
            extra_filters.append({
                "bool": {
                    "should": [
                        {"term": {"src": src_ip}},
                        {"term": {"initiator_ip": src_ip}},
                        {"term": {"original_initiator_ip": src_ip}},
                        {"term": {"client_ip": src_ip}},
                        {"term": {"source.ip": src_ip}},
                    ],
                    "minimum_should_match": 1,
                }
            })
        if dst_ip:
            extra_filters.append({
                "bool": {
                    "should": [
                        {"term": {"dst": dst_ip}},
                        {"term": {"responder_ip": dst_ip}},
                        {"term": {"destination.ip": dst_ip}},
                        {"term": {"xlatedst": dst_ip}},
                    ],
                    "minimum_should_match": 1,
                }
            })
        if dst_port is not None:
            extra_filters.append({
                "bool": {
                    "should": [
                        {"term": {"service": dst_port}},
                        {"term": {"s_port": dst_port}},
                        {"term": {"destination.port": dst_port}},
                        {"term": {"__p_dport": dst_port}},
                    ],
                    "minimum_should_match": 1,
                }
            })

        # --- Domain aggregation ---
        domain_body: dict[str, Any] = {
            "size": 0,
            "query": {"bool": {"filter": [time_range, *extra_filters], "should": ip_should, "minimum_should_match": 1}},
            "aggs": {
                "activity": {
                    "composite": {
                        "size": size,
                        "sources": [
                            {"domain": {"terms": {"script": {"lang": "painless", "source": DOMAIN_EXTRACTION_SCRIPT}}}},
                            {"application": {"terms": {"script": {"lang": "painless", "source": APPLICATION_EXTRACTION_SCRIPT}}}},
                        ],
                    },
                    "aggs": {
                        "first_seen": {"min": {"field": "@timestamp"}},
                        "last_seen": {"max": {"field": "@timestamp"}},
                    },
                }
            },
        }

        # --- Top IPs aggregation ---
        ips_body: dict[str, Any] = {
            "size": 0,
            "query": {"bool": {"filter": [time_range, *extra_filters], "should": ip_should, "minimum_should_match": 1}},
            "aggs": {
                "top_src": {"terms": {"field": "src", "size": 50}},
                "top_dst": {"terms": {"field": "dst", "size": 50}},
                "top_initiator": {"terms": {"field": "initiator_ip", "size": 50}},
                "top_responder": {"terms": {"field": "responder_ip", "size": 50}},
            },
        }

        # --- Top ports aggregation ---
        ports_body: dict[str, Any] = {
            "size": 0,
            "query": {"bool": {"filter": [time_range, *extra_filters], "should": ip_should, "minimum_should_match": 1}},
            "aggs": {
                "top_dst_port": {"terms": {"field": "service", "size": 50}},
                "top_src_port": {"terms": {"field": "s_port", "size": 50}},
            },
        }

        # --- Protocols + Actions + Users ---
        misc_body: dict[str, Any] = {
            "size": 0,
            "query": {"bool": {"filter": [time_range, *extra_filters], "should": ip_should, "minimum_should_match": 1}},
            "aggs": {
                "protocols": {"terms": {"field": "proto.keyword", "size": 20}},
                "actions": {"terms": {"field": "action.keyword", "size": 30}},
                "users": {"terms": {"field": "user.keyword", "size": 50}},
                "src_users": {"terms": {"field": "src_user_name.keyword", "size": 50}},
            },
        }

        # Search across all relevant indices
        index_patterns = [
            self.settings.opensearch_checkpoint_index_pattern,
            self.settings.opensearch_fmc_estreamer_index_pattern,
        ]

        all_domain_buckets: list[dict[str, Any]] = []
        seen_domain_keys: set[tuple[str, str]] = set()
        merged_ips: dict[str, dict[str, int]] = {"src": {}, "dst": {}, "initiator": {}, "responder": {}}
        merged_ports: dict[str, int] = {}
        merged_protocols: dict[str, int] = {}
        merged_actions: dict[str, int] = {}
        merged_users: dict[str, int] = {}
        total_hits = 0

        async with self._client() as client:
            for pattern in index_patterns:
                # Domains
                try:
                    r = await client.post(f"/{pattern}/_search", json=domain_body)
                    if r.status_code == 200:
                        for b in r.json().get("aggregations", {}).get("activity", {}).get("buckets", []):
                            key = (b.get("key", {}).get("domain", ""), b.get("key", {}).get("application", ""))
                            if key not in seen_domain_keys:
                                seen_domain_keys.add(key)
                                all_domain_buckets.append(b)
                except Exception:
                    pass

                # IPs
                try:
                    r = await client.post(f"/{pattern}/_search", json=ips_body)
                    if r.status_code == 200:
                        data = r.json()
                        total_hits += data.get("hits", {}).get("total", {}).get("value", 0)
                        aggs = data.get("aggregations", {})
                        for bucket in aggs.get("top_src", {}).get("buckets", []):
                            k = bucket["key"]
                            merged_ips["src"][k] = merged_ips["src"].get(k, 0) + bucket["doc_count"]
                        for bucket in aggs.get("top_dst", {}).get("buckets", []):
                            k = bucket["key"]
                            merged_ips["dst"][k] = merged_ips["dst"].get(k, 0) + bucket["doc_count"]
                        for bucket in aggs.get("top_initiator", {}).get("buckets", []):
                            k = bucket["key"]
                            merged_ips["initiator"][k] = merged_ips["initiator"].get(k, 0) + bucket["doc_count"]
                        for bucket in aggs.get("top_responder", {}).get("buckets", []):
                            k = bucket["key"]
                            merged_ips["responder"][k] = merged_ips["responder"].get(k, 0) + bucket["doc_count"]
                except Exception:
                    pass

                # Ports
                try:
                    r = await client.post(f"/{pattern}/_search", json=ports_body)
                    if r.status_code == 200:
                        aggs = r.json().get("aggregations", {})
                        for bucket in aggs.get("top_dst_port", {}).get("buckets", []):
                            k = str(bucket["key"])
                            merged_ports[k] = merged_ports.get(k, 0) + bucket["doc_count"]
                        for bucket in aggs.get("top_src_port", {}).get("buckets", []):
                            k = str(bucket["key"])
                            merged_ports[k] = merged_ports.get(k, 0) + bucket["doc_count"]
                except Exception:
                    pass

                # Misc (protocols, actions, users)
                try:
                    r = await client.post(f"/{pattern}/_search", json=misc_body)
                    if r.status_code == 200:
                        aggs = r.json().get("aggregations", {})
                        for bucket in aggs.get("protocols", {}).get("buckets", []):
                            k = bucket["key"]
                            merged_protocols[k] = merged_protocols.get(k, 0) + bucket["doc_count"]
                        for bucket in aggs.get("actions", {}).get("buckets", []):
                            k = bucket["key"]
                            merged_actions[k] = merged_actions.get(k, 0) + bucket["doc_count"]
                        for bucket in aggs.get("users", {}).get("buckets", []):
                            k = bucket["key"]
                            merged_users[k] = merged_users.get(k, 0) + bucket["doc_count"]
                        for bucket in aggs.get("src_users", {}).get("buckets", []):
                            k = bucket["key"]
                            merged_users[k] = merged_users.get(k, 0) + bucket["doc_count"]
                except Exception:
                    pass

        # Sort everything and filter unknowns
        all_domain_buckets = [
            b for b in all_domain_buckets
            if b.get("key", {}).get("domain", "") not in ("", "unknown", "-", "null")
        ]
        all_domain_buckets.sort(key=lambda b: b.get("doc_count", 0), reverse=True)

        def sort_dict(d: dict[str, int]) -> list[dict[str, Any]]:
            return [{"key": k, "doc_count": v} for k, v in sorted(d.items(), key=lambda x: x[1], reverse=True)[:size]]

        # ASN enrichment for all IPs
        all_ips: set[str] = set()
        for ip_dict in merged_ips.values():
            all_ips.update(ip_dict.keys())
        all_ips.add(ip)

        asn_map = self._enrich_ips_batch(list(all_ips))

        def enrich_ip_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            result = []
            for item in items:
                ip_addr = item["key"]
                geo_info = asn_map.get(ip_addr, {})
                result.append({
                    **item,
                    "asn": geo_info.get("asn"),
                    "asn_org": geo_info.get("asn_org"),
                    "vendor": geo_info.get("vendor", "Unknown"),
                    "category": geo_info.get("category", "unknown"),
                    "scope": geo_info.get("scope", "unknown"),
                    "country": geo_info.get("country"),
                    "country_name": geo_info.get("country_name"),
                })
            return result

        # Resolve protocol names
        resolved_protocols = [
            {"key": self._resolve_protocol(p["key"]), "doc_count": p["doc_count"]}
            for p in sort_dict(merged_protocols)
        ]

        return {
            "ip": ip,
            "start": start,
            "end": end,
            "total_hits": total_hits,
            "asn_info": asn_map.get(ip, {}),
            "domains": {
                "total": len(all_domain_buckets),
                "buckets": all_domain_buckets[:size],
            },
            "ips": {
                "as_source": enrich_ip_list(sort_dict(merged_ips["src"])),
                "as_destination": enrich_ip_list(sort_dict(merged_ips["dst"])),
                "as_initiator": enrich_ip_list(sort_dict(merged_ips["initiator"])),
                "as_responder": enrich_ip_list(sort_dict(merged_ips["responder"])),
            },
            "ports": sort_dict(merged_ports),
            "protocols": resolved_protocols,
            "actions": sort_dict(merged_actions),
            "users": sort_dict(merged_users),
        }

    # ------------------------------------------------------------------
    # ASN + Country enrichment
    # ------------------------------------------------------------------

    def _enrich_ips_batch(self, ips: list[str]) -> dict[str, dict[str, Any]]:
        """Enrich a list of IPs with ASN + Country data from GeoLite2."""
        try:
            from app.integrations.geoip.asn_enricher import enrich_ips
            results = enrich_ips(ips)
            return {r["ip"]: r for r in results}
        except Exception:
            return {}

    @staticmethod
    def _resolve_protocol(proto: str | None) -> str:
        """Map protocol number/name to human-readable name."""
        if not proto:
            return "—"
        proto_map = {
            "1": "ICMP", "6": "TCP", "17": "UDP", "47": "GRE",
            "50": "ESP", "51": "AH", "58": "ICMPv6", "89": "OSPF",
            "132": "SCTP",
        }
        p = str(proto).strip()
        if p in proto_map:
            return f"{proto_map[p]} ({p})"
        if p.lower() in ("tcp", "udp", "icmp", "gre", "esp"):
            return p.upper()
        return p

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _map_hits(
        self,
        data: dict[str, Any],
        mapping: OpenSearchSourceMapping,
        ip: str,
    ) -> list[UnifiedActivityEvent]:
        hits = data.get("hits", {}).get("hits", [])
        events: list[UnifiedActivityEvent] = []

        for hit in hits:
            source = hit.get("_source", {}) or {}

            source_ip = first_value(source, mapping.source_ip_fields)
            destination_ip = first_value(source, mapping.destination_ip_fields)

            event = UnifiedActivityEvent(
                source_name=mapping.name,
                index=hit.get("_index", ""),
                timestamp=as_str(get_value(source, mapping.timestamp_field)),
                source_ip=as_str(source_ip),
                source_port=as_int(first_value(source, mapping.source_port_fields)),
                destination_ip=as_str(destination_ip),
                destination_port=as_int(first_value(source, mapping.destination_port_fields)),
                protocol=as_str(first_value(source, mapping.protocol_fields)),
                action=as_str(first_value(source, mapping.action_fields)),
                application=as_str(first_value(source, mapping.application_fields)),
                rule=as_str(first_value(source, mapping.rule_fields)),
                policy=as_str(first_value(source, mapping.policy_fields)),
                user=as_str(first_value(source, mapping.user_fields)),
                domain=as_str(first_value(source, mapping.domain_fields)),
                url=as_str(first_value(source, mapping.url_fields)),
                bytes=sum_int_values(source, mapping.bytes_fields),
                packets=sum_int_values(source, mapping.packets_fields),
                is_source_ip=source_ip == ip,
                is_destination_ip=destination_ip == ip,
                raw=source,
            )

            if event.is_source_ip:
                event.direction = "outbound"
            elif event.is_destination_ip:
                event.direction = "inbound"
            else:
                event.direction = "related"

            events.append(event)

        return events

    def _build_summary_from_events(
            self,
            ip: str,
            events: list[UnifiedActivityEvent],
            window: str,
    ) -> ActivitySummary:
        internal_counter: dict[tuple[str, int | None], int] = {}
        external_counter: dict[tuple[str, int | None], int] = {}

        internal_ports: dict[int, int] = {}
        external_ports: dict[int, int] = {}
        domain_counter: dict[str, int] = {}

        source_stats: dict[str, int] = {}
        index_stats: dict[str, int] = {}

        users: set[str] = set()

        internal_count = 0
        external_count = 0
        security_events = 0

        for event in events:
            if event.source_name:
                source_stats[event.source_name] = source_stats.get(event.source_name, 0) + 1

            if event.index:
                index_stats[event.index] = index_stats.get(event.index, 0) + 1

            extracted_user = self._extract_user_from_event(event)
            if extracted_user:
                users.add(extracted_user)

            if event.domain:
                domain_counter[event.domain] = domain_counter.get(event.domain, 0) + 1

            peer_ip = None
            peer_port = None

            if event.source_ip == ip:
                peer_ip = event.destination_ip
                peer_port = event.destination_port
            elif event.destination_ip == ip:
                peer_ip = event.source_ip
                peer_port = event.source_port

            if not peer_ip:
                continue

            action = (event.action or "").lower()

            if action in self._all_block_actions():
                security_events += 1

            key = (peer_ip, peer_port)

            if self._is_internal_ip(peer_ip):
                internal_count += 1
                internal_counter[key] = internal_counter.get(key, 0) + 1

                if peer_port:
                    internal_ports[peer_port] = internal_ports.get(peer_port, 0) + 1
            else:
                external_count += 1
                external_counter[key] = external_counter.get(key, 0) + 1

                if peer_port:
                    external_ports[peer_port] = external_ports.get(peer_port, 0) + 1

        sorted_users = sorted(users)

        return ActivitySummary(
            window=window,
            user=sorted_users[0] if sorted_users else None,
            users=sorted_users,
            internal_connections=internal_count,
            external_connections=external_count,
            security_events=security_events,
            top_internal_destinations=self._counter_to_counterparties(internal_counter)[:10],
            top_external_destinations=self._counter_to_counterparties(external_counter)[:10],
            top_internal_ports=self._counter_to_ports(internal_ports)[:10],
            top_external_ports=self._counter_to_ports(external_ports)[:10],
            top_domains=self._counter_to_domains(domain_counter)[:10],
            source_stats=source_stats,
            index_stats=index_stats,
            events=events[:300],
            status=IntegrationStatus(status="ok"),
        )

    def _all_block_actions(self) -> set[str]:
        result: set[str] = set()

        for mapping in self._source_mappings():
            result.update(action.lower() for action in mapping.block_actions)

        return result

    def _counter_to_counterparties(
        self,
        counter: dict[tuple[str, int | None], int],
    ) -> list[ActivityCounterparty]:
        items = sorted(
            counter.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        return [
            ActivityCounterparty(
                ip=peer_ip,
                port=port,
                service=None,
                count=count,
            )
            for (peer_ip, port), count in items
        ]

    def _is_internal_ip(self, value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False

        return any(address in network for network in self._internal_networks)
