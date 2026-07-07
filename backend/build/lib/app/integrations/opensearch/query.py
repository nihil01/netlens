from __future__ import annotations

from typing import Any

from app.integrations.opensearch.mappings import OpenSearchSourceMapping


def field_terms(fields: list[str], value: str | int) -> list[dict[str, Any]]:
    """Return a list of ``term`` clauses, one per field."""
    return [{"term": {field: value}} for field in fields]


def build_time_range(
    timestamp_field: str,
    window: str,
    start: str | None,
    end: str | None,
) -> dict[str, Any]:
    """Build an OpenSearch ``range`` clause for the given timestamp field."""
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
    """Build the full OpenSearch query body for IP log retrieval."""
    time_range = build_time_range(
        timestamp_field=mapping.timestamp_field,
        window=window,
        start=start,
        end=end,
    )

    directional_filters: list[dict[str, Any]] = []
    ip_should = [
        {"term": {field: ip}}
        for field in mapping.source_ip_fields + mapping.destination_ip_fields
    ]

    if src_ip:
        directional_filters.append({
            "bool": {
                "should": field_terms(mapping.source_ip_fields, src_ip),
                "minimum_should_match": 1,
            }
        })

    if dst_ip:
        directional_filters.append({
            "bool": {
                "should": field_terms(mapping.destination_ip_fields, dst_ip),
                "minimum_should_match": 1,
            }
        })

    if dst_port is not None:
        directional_filters.append({
            "bool": {
                "should": field_terms(mapping.destination_port_fields, dst_port),
                "minimum_should_match": 1,
            }
        })

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
                    *directional_filters,
                ],
                **({"should": ip_should, "minimum_should_match": 1} if not directional_filters else {}),
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
