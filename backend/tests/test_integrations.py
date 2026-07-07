from app.core.config import Settings
from app.integrations.netbox.service import NetBoxService
from app.integrations.opensearch.service import OpenSearchActivityService
from app.ip_intelligence.schemas import IntegrationStatus
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


def test_opensearch_query_template_uses_configured_fields() -> None:
    settings = Settings(
        opensearch_url="https://os.example.com:9200",
        opensearch_index_pattern="checkpoint-*,fmc-*",
        opensearch_source_ip_fields=["src_ip"],
        opensearch_destination_ip_fields=["dst_ip"],
        opensearch_destination_port_field="dst_port",
        opensearch_action_field="action",
    )
    query = OpenSearchActivityService(settings).build_ip_activity_query("10.1.1.10")

    assert query["query"]["bool"]["filter"][0]["range"]["@timestamp"]["gte"] == "now-24h"
    assert {"term": {"src_ip": "10.1.1.10"}} in query["query"]["bool"]["should"]
    assert {"term": {"dst_ip": "10.1.1.10"}} in query["query"]["bool"]["should"]
    aggs = query["aggs"]["as_source"]["aggs"]["top_destinations"]
    assert aggs["terms"]["field"] == "dst_ip"
    assert aggs["aggs"]["top_port"]["terms"]["field"] == "dst_port"
    assert "action" in query["aggs"]["security_events"]["filter"]["terms"]


def test_opensearch_response_maps_internal_external_and_security_counts() -> None:
    service = OpenSearchActivityService(Settings(opensearch_url="https://os.example.com:9200"))
    summary = service._map_response(
        {
            "aggregations": {
                "as_source": {
                    "top_destinations": {
                        "buckets": [
                            {
                                "key": "10.10.10.20",
                                "doc_count": 7,
                                "top_port": {"buckets": [{"key": 443}]},
                            },
                            {
                                "key": "8.8.8.8",
                                "doc_count": 3,
                                "top_port": {"buckets": [{"key": 53}]},
                            },
                        ]
                    }
                },
                "security_events": {"doc_count": 2},
            }
        },
        window="24h",
    )

    assert summary.internal_connections == 7
    assert summary.external_connections == 3
    assert summary.security_events == 2
    assert summary.top_internal_destinations[0].ip == "10.10.10.20"
    assert summary.top_external_destinations[0].ip == "8.8.8.8"


def test_scanner_scheduler_does_not_start_when_disabled() -> None:
    scheduler = ScannerScheduler(Settings(scanner_schedule_enabled=False))
    scheduler.start()

    assert scheduler.scheduler.running is False


def test_integration_status_contract() -> None:
    status = IntegrationStatus(status="not_configured", message="missing")

    assert status.status == "not_configured"
    assert status.message == "missing"
