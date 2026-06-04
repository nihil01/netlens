import ipaddress
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.ip_intelligence.schemas import ActivityCounterparty, ActivitySummary, IntegrationStatus


class OpenSearchActivityService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._internal_networks = [ipaddress.ip_network(cidr) for cidr in settings.internal_cidrs]

    @classmethod
    def from_settings(cls) -> "OpenSearchActivityService":
        return cls(get_settings())

    async def summarize_ip(self, ip: str, window: str = "24h") -> ActivitySummary:
        if not self.settings.opensearch_url:
            return ActivitySummary(
                window=window,
                status=IntegrationStatus(
                    status="not_configured",
                    message="OPENSEARCH_URL is required",
                ),
            )

        try:
            async with self._client() as client:
                body = self.build_ip_activity_query(ip=ip, window=window)
                response = await client.post(
                    f"/{self.settings.opensearch_index_pattern}/_search",
                    json=body,
                )
                response.raise_for_status()
                return self._map_response(response.json(), window)
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
            auth = (self.settings.opensearch_username, self.settings.opensearch_password)
        return httpx.AsyncClient(
            base_url=str(self.settings.opensearch_url).rstrip("/"),
            auth=auth,
            verify=self.settings.opensearch_verify_ssl,
            timeout=self.settings.opensearch_timeout_seconds,
        )

    def build_ip_activity_query(self, ip: str, window: str = "24h") -> dict[str, Any]:
        timestamp = self.settings.opensearch_timestamp_field
        source_should = [
            {"term": {field: ip}} for field in self.settings.opensearch_source_ip_fields
        ]
        peer_should = source_should + [
            {"term": {field: ip}} for field in self.settings.opensearch_destination_ip_fields
        ]
        destination_ip_field = self.settings.opensearch_destination_ip_fields[0]

        return {
            "size": 0,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "filter": [{"range": {timestamp: {"gte": f"now-{window}", "lte": "now"}}}],
                    "should": peer_should,
                    "minimum_should_match": 1,
                }
            },
            "aggs": {
                "as_source": {
                    "filter": {"bool": {"should": source_should, "minimum_should_match": 1}},
                    "aggs": {
                        "top_destinations": {
                            "terms": {
                                "field": destination_ip_field,
                                "size": 20,
                                "missing": "unknown",
                            },
                            "aggs": {
                                "top_port": {
                                    "terms": {
                                        "field": self.settings.opensearch_destination_port_field,
                                        "size": 1,
                                        "missing": -1,
                                    }
                                }
                            },
                        }
                    },
                },
                "security_events": {
                    "filter": {
                        "terms": {
                            self.settings.opensearch_action_field: (
                                self.settings.opensearch_block_actions
                            )
                        }
                    }
                },
            },
        }

    def _map_response(self, data: dict[str, Any], window: str) -> ActivitySummary:
        buckets = (
            data.get("aggregations", {})
            .get("as_source", {})
            .get("top_destinations", {})
            .get("buckets", [])
        )
        internal: list[ActivityCounterparty] = []
        external: list[ActivityCounterparty] = []
        internal_count = 0
        external_count = 0

        for bucket in buckets:
            peer_ip = str(bucket.get("key"))
            count = int(bucket.get("doc_count", 0))
            port = self._extract_top_port(bucket)
            item = ActivityCounterparty(ip=peer_ip, port=port, service=None, count=count)
            if self._is_internal_ip(peer_ip):
                internal.append(item)
                internal_count += count
            else:
                external.append(item)
                external_count += count

        security_events = int(
            data.get("aggregations", {}).get("security_events", {}).get("doc_count", 0)
        )
        return ActivitySummary(
            window=window,
            internal_connections=internal_count,
            external_connections=external_count,
            security_events=security_events,
            top_internal_destinations=internal[:10],
            top_external_destinations=external[:10],
        )

    @staticmethod
    def _extract_top_port(bucket: dict[str, Any]) -> int | None:
        ports = bucket.get("top_port", {}).get("buckets", [])
        if not ports:
            return None
        value = ports[0].get("key")
        return None if value in (None, -1, "-1") else int(value)

    def _is_internal_ip(self, value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        return any(address in network for network in self._internal_networks)
