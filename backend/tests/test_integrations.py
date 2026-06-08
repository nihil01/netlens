from app.core.config import Settings
from app.integrations.netbox.service import NetBoxService
from app.integrations.opensearch.service import OpenSearchActivityService
from app.ip_intelligence.schemas import IntegrationStatus, UnifiedActivityEvent
from app.scanner.scheduler import ScannerScheduler


def test_netbox_mapping_extracts_device_site_region_and_interfaces() -> None:
    service = NetBoxService(Settings(netbox_url="https://netbox.example.com", netbox_token="token"))
    context = service._map_context(
        ip_object={"address": "10.1.1.10/32"},
        device={
            "id": 10,
            "name": "SW-BAKU-01",
            "site": {"name": "Baku HQ", "region": {"name": "Baku"}},
            "location": {"name": "Building A"},
            "role": {"name": "switch"},
        },
        interfaces=[{"name": "Gi1/0/1"}],
    )

    assert context.known is True
    assert context.device == "SW-BAKU-01"
    assert context.site == "Baku HQ"
    assert context.region == "Baku"
    assert context.city == "Building A"
    assert context.role == "switch"
    assert context.interfaces == [{"name": "Gi1/0/1"}]


def test_opensearch_query_template_uses_configured_source_mapping_fields() -> None:
    service = OpenSearchActivityService(Settings(opensearch_url="https://os.example.com:9200"))
    mapping = service._source_mappings()[0]
    query = service.build_ip_logs_query(mapping=mapping, ip="10.1.1.10")

    assert query["query"]["bool"]["filter"][0]["range"]["@timestamp"]["gte"] == "now-24h"
    assert {"term": {"source.ip": "10.1.1.10"}} in query["query"]["bool"]["should"]
    assert {"term": {"destination.ip": "10.1.1.10"}} in query["query"]["bool"]["should"]
    assert query["query"]["bool"]["minimum_should_match"] == 1
    assert "source.ip" in query["_source"]["includes"]
    assert "destination.port" in query["_source"]["includes"]


def test_opensearch_query_applies_directional_filters() -> None:
    service = OpenSearchActivityService(Settings(opensearch_url="https://os.example.com:9200"))
    mapping = service._source_mappings()[0]
    query = service.build_ip_logs_query(
        mapping=mapping,
        ip="10.1.1.10",
        src_ip="10.1.1.10",
        dst_ip="8.8.8.8",
        dst_port=53,
    )

    bool_query = query["query"]["bool"]
    assert {
        "bool": {
            "should": [{"term": {"source.ip": "10.1.1.10"}}],
            "minimum_should_match": 1,
        }
    } in bool_query["filter"]
    assert {
        "bool": {
            "should": [{"term": {"destination.ip": "8.8.8.8"}}],
            "minimum_should_match": 1,
        }
    } in bool_query["filter"]
    assert {
        "bool": {
            "should": [{"term": {"destination.port": 53}}],
            "minimum_should_match": 1,
        }
    } in bool_query["filter"]
    assert "should" not in bool_query


def test_opensearch_events_map_internal_external_and_security_counts() -> None:
    service = OpenSearchActivityService(Settings(opensearch_url="https://os.example.com:9200"))
    summary = service._build_summary_from_events(
        ip="10.1.1.10",
        window="24h",
        events=[
            UnifiedActivityEvent(
                source_name="firepower",
                index="firepower-1",
                source_ip="10.1.1.10",
                destination_ip="10.10.10.20",
                destination_port=443,
                action="allow",
            ),
            UnifiedActivityEvent(
                source_name="firepower",
                index="firepower-1",
                source_ip="10.1.1.10",
                destination_ip="8.8.8.8",
                destination_port=53,
                action="blocked",
            ),
        ],
    )

    assert summary.internal_connections == 1
    assert summary.external_connections == 1
    assert summary.security_events == 1
    assert summary.top_internal_destinations[0].ip == "10.10.10.20"
    assert summary.top_external_destinations[0].ip == "8.8.8.8"
    assert summary.top_external_ports[0].port == 53
    assert summary.source_stats == {"firepower": 2}
    assert summary.index_stats == {"firepower-1": 2}


def test_scanner_scheduler_does_not_start_when_disabled() -> None:
    scheduler = ScannerScheduler(Settings(scanner_schedule_enabled=False))
    scheduler.start()

    assert scheduler.scheduler.running is False


def test_integration_status_contract() -> None:
    status = IntegrationStatus(status="not_configured", message="missing")

    assert status.status == "not_configured"
    assert status.message == "missing"
