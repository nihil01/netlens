import ipaddress
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.ip_intelligence.schemas import (
    ActivityCounterparty,
    ActivitySummary,
    IntegrationStatus,
    UnifiedActivityEvent,
)


@dataclass(frozen=True)
class OpenSearchSourceMapping:
    name: str
    index_pattern: str
    timestamp_field: str

    source_ip_fields: list[str]
    destination_ip_fields: list[str]

    source_port_fields: list[str] = field(default_factory=list)
    destination_port_fields: list[str] = field(default_factory=list)

    protocol_fields: list[str] = field(default_factory=list)
    action_fields: list[str] = field(default_factory=list)
    application_fields: list[str] = field(default_factory=list)
    rule_fields: list[str] = field(default_factory=list)
    policy_fields: list[str] = field(default_factory=list)
    user_fields: list[str] = field(default_factory=list)
    domain_fields: list[str] = field(default_factory=list)
    url_fields: list[str] = field(default_factory=list)

    bytes_fields: list[str] = field(default_factory=list)
    packets_fields: list[str] = field(default_factory=list)

    block_actions: set[str] = field(default_factory=set)


class OpenSearchActivityService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._internal_networks = [
            ipaddress.ip_network(cidr)
            for cidr in settings.internal_cidrs
        ]

    @classmethod
    def from_settings(cls) -> "OpenSearchActivityService":
        return cls(get_settings())

    async def summarize_ip(
        self,
        ip: str,
        window: str = "24h",
        start: str | None = None,
        end: str | None = None,
        size_per_source: int = 100,
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
                    )

                    response = await client.post(
                        f"/{mapping.index_pattern}/_search",
                        json=body,
                    )

                    response.raise_for_status()

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

    def _client(self) -> httpx.AsyncClient:
        auth = None

        if self.settings.opensearch_username and self.settings.opensearch_password:
            auth = (
                self.settings.opensearch_username,
                self.settings.opensearch_password,
            )

        return httpx.AsyncClient(
            base_url=str(self.settings.opensearch_url).rstrip("/"),
            auth=auth,
            verify=self.settings.opensearch_verify_ssl,
            timeout=self.settings.opensearch_timeout_seconds,
        )

    def _source_mappings(self) -> list[OpenSearchSourceMapping]:
        return [
            OpenSearchSourceMapping(
                name="firepower",
                index_pattern=self.settings.opensearch_firepower_index_pattern,
                timestamp_field="@timestamp",
                source_ip_fields=["source.ip"],
                destination_ip_fields=["destination.ip"],
                source_port_fields=["source.port"],
                destination_port_fields=["destination.port"],
                protocol_fields=["network.transport"],
                action_fields=["event.action"],
                application_fields=["application", "network.application"],
                rule_fields=["rule.name", "firewall_rule"],
                policy_fields=["policy.name", "firewall_policy"],
                user_fields=["user.name"],
                domain_fields=[
                    "url.domain",
                    "dns.question.name",
                    "tls.server.x509.subject.common_name",
                ],
                url_fields=["url.full", "url.original", "message"],
                bytes_fields=["network.bytes"],
                block_actions={"block", "blocked", "deny", "denied", "drop", "dropped"},
            ),
            OpenSearchSourceMapping(
                name="fmc_estreamer",
                index_pattern=self.settings.opensearch_fmc_estreamer_index_pattern,
                timestamp_field="@timestamp",
                source_ip_fields=[
                    "initiator_ip",
                    "original_initiator_ip",
                    "extra_fields.NAT_InitiatorIP",
                ],
                destination_ip_fields=[
                    "responder_ip",
                    "extra_fields.NAT_ResponderIP",
                ],
                source_port_fields=[
                    "initiator_port",
                    "extra_fields.NAT_InitiatorPort",
                ],
                destination_port_fields=[
                    "responder_port",
                    "extra_fields.NAT_ResponderPort",
                ],
                protocol_fields=["protocol"],
                action_fields=[
                    "extra_fields.AC_RuleAction",
                    "event_type.keyword",
                    "event_type",
                ],
                application_fields=[
                    "application.keyword",
                    "application",
                    "client_application.keyword",
                    "client_application",
                    "web_application.keyword",
                    "web_application",
                ],
                rule_fields=[
                    "firewall_rule.keyword",
                    "firewall_rule",
                ],
                policy_fields=[
                    "firewall_policy.keyword",
                    "firewall_policy",
                    "prefilter_policy.keyword",
                    "prefilter_policy",
                ],
                domain_fields=[
                    "referenced_host.keyword",
                    "referenced_host",
                    "extra_fields.DNS_Query.keyword",
                    "extra_fields.DNS_Query",
                ],
                url_fields=[
                    "url.keyword",
                    "url",
                    "extra_fields.URI.keyword",
                    "extra_fields.URI",
                    "extra_fields.HTTP_Referer.keyword",
                    "extra_fields.HTTP_Referer",
                ],
                bytes_fields=[
                    "initiator_bytes",
                    "responder_bytes",
                ],
                packets_fields=[
                    "initiator_packets",
                    "responder_packets",
                ],
                block_actions={"block", "blocked", "deny", "denied", "drop", "dropped"},
            ),
            OpenSearchSourceMapping(
                name="checkpoint",
                index_pattern=self.settings.opensearch_checkpoint_index_pattern,
                timestamp_field="@timestamp",
                source_ip_fields=[
                    "src",
                    "client_ip.keyword",
                    "client_ip",
                    "endpoint_ip.keyword",
                    "endpoint_ip",
                    "xlatesrc",
                    "proxy_src_ip.keyword",
                    "proxy_src_ip",
                ],
                destination_ip_fields=[
                    "dst",
                    "xlatedst",
                ],
                source_port_fields=[
                    "s_port",
                    "xlatesport.keyword",
                    "xlatesport",
                ],
                destination_port_fields=[
                    "service",
                    "__p_dport.keyword",
                    "__p_dport",
                    "xlatedport.keyword",
                    "xlatedport",
                ],
                protocol_fields=[
                    "proto.keyword",
                    "proto",
                    "protocol.keyword",
                    "protocol",
                ],
                action_fields=[
                    "action.keyword",
                    "action",
                    "rule_action.keyword",
                    "rule_action",
                ],
                application_fields=[
                    "appi_name.keyword",
                    "appi_name",
                    "app_id.keyword",
                    "app_id",
                    "app_category.keyword",
                    "app_category",
                ],
                rule_fields=[
                    "rule_name.keyword",
                    "rule_name",
                    "rule.keyword",
                    "rule",
                    "rule_uid.keyword",
                    "rule_uid",
                ],
                policy_fields=[
                    "policy.keyword",
                    "policy",
                    "layer_name.keyword",
                    "layer_name",
                ],
                user_fields=[
                    "user.keyword",
                    "user",
                    "src_user_name.keyword",
                    "src_user_name",
                    "dst_user_name.keyword",
                    "dst_user_name",
                ],
                domain_fields=[
                    "domain.keyword",
                    "domain",
                    "domain_name.keyword",
                    "domain_name",
                    "src_domain_name.keyword",
                    "src_domain_name",
                    "dst_domain_name.keyword",
                    "dst_domain_name",
                    "http_host.keyword",
                    "http_host",
                    "sni.keyword",
                    "sni",
                    "tls_server_host_name.keyword",
                    "tls_server_host_name",
                ],
                url_fields=[
                    "resource.keyword",
                    "resource",
                    "url.keyword",
                    "url",
                    "referrer.keyword",
                    "referrer",
                ],
                bytes_fields=[
                    "bytes",
                    "client_inbound_bytes",
                    "client_outbound_bytes",
                    "server_inbound_bytes",
                    "server_outbound_bytes",
                ],
                packets_fields=[
                    "packets",
                    "client_inbound_packets",
                    "client_outbound_packets",
                    "server_inbound_packets",
                    "server_outbound_packets",
                ],
                block_actions={
                    "drop",
                    "dropped",
                    "deny",
                    "denied",
                    "reject",
                    "prevent",
                    "blocked",
                    "block",
                },
            ),
        ]

    def build_ip_logs_query(
        self,
        mapping: OpenSearchSourceMapping,
        ip: str,
        window: str = "24h",
        start: str | None = None,
        end: str | None = None,
        size: int = 100,
    ) -> dict[str, Any]:
        time_range = self._build_time_range(
            timestamp_field=mapping.timestamp_field,
            window=window,
            start=start,
            end=end,
        )

        ip_should = [
            {"term": {field: ip}}
            for field in mapping.source_ip_fields + mapping.destination_ip_fields
        ]

        source_includes = sorted(
            {
                mapping.timestamp_field,
                *mapping.source_ip_fields,
                *mapping.destination_ip_fields,
                *mapping.source_port_fields,
                *mapping.destination_port_fields,
                *mapping.protocol_fields,
                *mapping.action_fields,
                *mapping.application_fields,
                *mapping.rule_fields,
                *mapping.policy_fields,
                *mapping.user_fields,
                *mapping.domain_fields,
                *mapping.url_fields,
                *mapping.bytes_fields,
                *mapping.packets_fields,
            }
        )

        return {
            "size": size,
            "track_total_hits": True,
            "_source": {
                "includes": source_includes,
            },
            "query": {
                "bool": {
                    "filter": [
                        time_range,
                    ],
                    "should": ip_should,
                    "minimum_should_match": 1,
                }
            },
            "sort": [
                {
                    mapping.timestamp_field: {
                        "order": "desc",
                        "unmapped_type": "date",
                    }
                }
            ],
        }

    def _build_time_range(
        self,
        timestamp_field: str,
        window: str,
        start: str | None,
        end: str | None,
    ) -> dict[str, Any]:
        if start:
            return {
                "range": {
                    timestamp_field: {
                        "gte": start,
                        "lte": end or "now",
                    }
                }
            }

        return {
            "range": {
                timestamp_field: {
                    "gte": f"now-{window}",
                    "lte": "now",
                }
            }
        }

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

            source_ip = self._first_value(source, mapping.source_ip_fields)
            destination_ip = self._first_value(source, mapping.destination_ip_fields)

            event = UnifiedActivityEvent(
                source_name=mapping.name,
                index=hit.get("_index", ""),
                timestamp=self._as_str(self._get_value(source, mapping.timestamp_field)),
                source_ip=self._as_str(source_ip),
                source_port=self._as_int(self._first_value(source, mapping.source_port_fields)),
                destination_ip=self._as_str(destination_ip),
                destination_port=self._as_int(self._first_value(source, mapping.destination_port_fields)),
                protocol=self._as_str(self._first_value(source, mapping.protocol_fields)),
                action=self._as_str(self._first_value(source, mapping.action_fields)),
                application=self._as_str(self._first_value(source, mapping.application_fields)),
                rule=self._as_str(self._first_value(source, mapping.rule_fields)),
                policy=self._as_str(self._first_value(source, mapping.policy_fields)),
                user=self._as_str(self._first_value(source, mapping.user_fields)),
                domain=self._as_str(self._first_value(source, mapping.domain_fields)),
                url=self._as_str(self._first_value(source, mapping.url_fields)),
                bytes=self._sum_int_values(source, mapping.bytes_fields),
                packets=self._sum_int_values(source, mapping.packets_fields),
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

        internal_count = 0
        external_count = 0
        security_events = 0

        for event in events:
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

            key = (peer_ip, peer_port)
            action = (event.action or "").lower()

            if action in self._all_block_actions():
                security_events += 1

            if self._is_internal_ip(peer_ip):
                internal_count += 1
                internal_counter[key] = internal_counter.get(key, 0) + 1
            else:
                external_count += 1
                external_counter[key] = external_counter.get(key, 0) + 1

        top_internal = self._counter_to_counterparties(internal_counter)
        top_external = self._counter_to_counterparties(external_counter)

        return ActivitySummary(
            window=window,
            internal_connections=internal_count,
            external_connections=external_count,
            security_events=security_events,
            top_internal_destinations=top_internal[:10],
            top_external_destinations=top_external[:10],
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

    def _first_value(
        self,
        source: dict[str, Any],
        fields: list[str],
    ) -> Any:
        for field in fields:
            value = self._get_value(source, field)

            if value not in (None, "", [], {}):
                return value

        return None

    def _get_value(
        self,
        source: dict[str, Any],
        dotted_path: str,
    ) -> Any:
        current: Any = source

        for part in dotted_path.split("."):
            if not isinstance(current, dict):
                return None

            current = current.get(part)

            if current is None:
                return None

        return current

    def _sum_int_values(
        self,
        source: dict[str, Any],
        fields: list[str],
    ) -> int | None:
        total = 0
        found = False

        for field in fields:
            value = self._as_int(self._get_value(source, field))

            if value is not None:
                total += value
                found = True

        return total if found else None

    @staticmethod
    def _as_str(value: Any) -> str | None:
        if value in (None, "", [], {}):
            return None

        if isinstance(value, list):
            return ", ".join(str(item) for item in value if item not in (None, ""))

        return str(value)

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value in (None, "", [], {}):
            return None

        if isinstance(value, list):
            value = value[0] if value else None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None