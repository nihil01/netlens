"""Tests for FMC Audit & Change Intelligence module."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.integrations.fmc_audit.client import FmcAuditClient
from app.integrations.fmc_audit.collector import FmcAuditCollector
from app.integrations.fmc_audit.schemas import AuditRecordDto
from app.integrations.fmc_audit.service import FmcAuditService


@pytest.fixture
def service():
    return FmcAuditService.__new__(FmcAuditService)


class TestRiskScoring:
    def test_delete_action_high_risk(self, service):
        rec = AuditRecordDto(
            fmc_id="test-1",
            timestamp=datetime(2026, 7, 30, 2, 30, tzinfo=UTC),
            action="DELETE",
            object_type="AccessPolicy",
            changed_fields=["action", "networks"],
        )
        score, factors = service._compute_risk(rec)
        assert score >= 70
        assert "delete_action" in factors
        assert "high_risk_object:AccessPolicy" in factors
        assert "off_hours" in factors

    def test_add_action_low_risk(self, service):
        rec = AuditRecordDto(
            fmc_id="test-2",
            timestamp=datetime(2026, 7, 30, 14, 0, tzinfo=UTC),
            action="ADD",
            object_type="NetworkObject",
        )
        score, factors = service._compute_risk(rec)
        assert score < 30
        assert "add_action" in factors

    def test_update_medium_risk(self, service):
        rec = AuditRecordDto(
            fmc_id="test-3",
            timestamp=datetime(2026, 7, 30, 14, 0, tzinfo=UTC),
            action="UPDATE",
            object_type="ACLPolicy",
            changed_fields=["enabled", "networks"],
        )
        score, factors = service._compute_risk(rec)
        assert 30 <= score < 70

    def test_risk_capped_at_100(self, service):
        rec = AuditRecordDto(
            fmc_id="test-4",
            timestamp=datetime(2026, 7, 30, 2, 0, tzinfo=UTC),
            action="DELETE",
            object_type="AccessPolicy",
            changed_fields=["action", "networks", "securityZone"],
            refs_added=[{"type": "ref"}],
        )
        score, _ = service._compute_risk(rec)
        assert score <= 100


class TestDiffComputation:
    def test_modified_fields(self, service):
        before = {"name": "old", "enabled": True}
        after = {"name": "new", "enabled": False}
        diffs = service._compute_diffs(before, after)
        assert len(diffs) == 2
        assert all(d.change_type == "modified" for d in diffs)

    def test_added_field(self, service):
        before = {"name": "old"}
        after = {"name": "old", "new_field": "value"}
        diffs = service._compute_diffs(before, after)
        assert len(diffs) == 1
        assert diffs[0].change_type == "added"

    def test_removed_field(self, service):
        before = {"name": "old", "extra": "value"}
        after = {"name": "old"}
        diffs = service._compute_diffs(before, after)
        assert len(diffs) == 1
        assert diffs[0].change_type == "removed"

    def test_empty_before_after(self, service):
        diffs = service._compute_diffs(None, None)
        assert diffs == []

    def test_identical(self, service):
        data = {"name": "test", "value": 42}
        diffs = service._compute_diffs(data, data)
        assert diffs == []


class TestTimeline:
    def test_build_timeline(self, service):
        from app.integrations.fmc_audit.models import AuditRecord

        records = []
        for i in range(5):
            r = AuditRecord()
            r.timestamp = datetime(2026, 7, 30, 10, i, tzinfo=UTC)
            r.action = "UPDATE" if i % 2 == 0 else "ADD"
            r.risk_score = 50 if i == 2 else 10
            records.append(r)
        timeline = service._build_timeline(records)
        assert len(timeline) == 1
        assert timeline[0]["total"] == 5
        assert timeline[0]["updates"] == 3
        assert timeline[0]["adds"] == 2
        assert timeline[0]["high_risk"] == 1


class TestAuditNormalization:
    @pytest.fixture
    def collector(self):
        return FmcAuditCollector(
            Settings(fmc_url="https://fmc", fmc_username="reader", fmc_password="secret")
        )

    def test_epoch_timestamp_and_distinct_ids(self, collector):
        dto = collector._normalize_audit_record(
            {
                "id": "record-1",
                "auditId": "audit-7",
                "snapshotId": "snapshot-9",
                "time": 1460055526,
                "username": "noc",
                "subSystem": "API",
            }
        )

        assert dto.fmc_id == "record-1"
        assert dto.record_id == "record-1"
        assert dto.audit_id == "audit-7"
        assert dto.snapshot_id == "snapshot-9"
        assert dto.timestamp == datetime.fromtimestamp(1460055526, tz=UTC)
        assert dto.local_timestamp.utcoffset().total_seconds() == 4 * 3600

    def test_config_change_aliases_build_diff_without_using_record_id(self, collector):
        dto = collector._normalize_audit_record(
            {
                "id": "record-not-audit-id",
                "auditId": "audit-id",
                "snapshotId": "snapshot-id",
                "_netlensConfigChanges": [
                    {
                        "entityId": "entity-1",
                        "entityType": "AccessPolicy",
                        "entityName": "ACP",
                        "action": "update",
                        "valuesUpdated": [
                            {"fieldName": "enabled", "oldValue": False, "newValue": True}
                        ],
                        "referencesAdded": [{"id": "ref-1"}],
                    }
                ],
            }
        )

        assert dto.object_id == "entity-1"
        assert dto.action == "UPDATE"
        assert dto.before_json == {"enabled": False}
        assert dto.after_json == {"enabled": True}
        assert dto.refs_added == [{"id": "ref-1"}]

    def test_missing_ids_get_nonempty_stable_content_identifier(self, collector):
        raw = {"time": 1460055526, "message": "Login Success"}
        first = collector._normalize_audit_record(raw)
        second = collector._normalize_audit_record(raw)
        assert first.fmc_id.startswith("content:")
        assert first.fmc_id == second.fmc_id

    def test_missing_event_time_remains_unknown(self, collector):
        dto = collector._normalize_audit_record({"id": "record-no-time", "message": "fact"})
        assert dto.timestamp is None
        assert dto.local_timestamp is None

    def test_password_values_and_inline_tokens_are_masked(self, collector):
        dto = collector._normalize_audit_record(
            {
                "id": "record-1",
                "message": "token=plain-secret",
                "valueUpdated": [{"fieldName": "password", "oldValue": "old", "newValue": "new"}],
            }
        )
        assert "plain-secret" not in str(dto.raw_json)
        assert dto.values_updated[0]["oldValue"] == "***"
        assert dto.values_updated[0]["newValue"] == "***"

    def test_job_history_field_names_are_normalized(self, collector):
        dto = collector._normalize_deployment(
            {
                "id": "job-1",
                "jobName": "Deploy_Job_1",
                "jobStatus": "Deployed",
                "user": "admin",
                "deviceList": [
                    {"deviceUUID": "one", "deploymentStatus": "SUCCEEDED"},
                    {"deviceUUID": "two", "deploymentStatus": "FAILED"},
                ],
            }
        )
        assert dto.name == "Deploy_Job_1"
        assert dto.status == "DEPLOYED"
        assert dto.success_count == 1
        assert dto.failed_count == 1


@pytest.mark.asyncio
async def test_audit_client_uses_platform_ids_and_jobhistory_endpoint() -> None:
    client = FmcAuditClient(
        Settings(fmc_url="https://fmc", fmc_username="reader", fmc_password="secret")
    )
    client._domain_uuid = "domain"
    client.get_all = AsyncMock(return_value=[])

    await client.get_config_changes(audit_log_id="audit/id", snapshot_id="snapshot/id")
    config_path = client.get_all.await_args.args[0]
    assert config_path.startswith("/api/fmc_platform/v1/domain/domain/audit/configchanges?")
    assert "auditLogId=audit%2Fid" in config_path
    assert "snapshotId=snapshot%2Fid" in config_path

    await client.get_all_deployments()
    deployment_path = client.get_all.await_args.args[0]
    assert deployment_path.endswith("/deployment/jobhistories")

    await client.get_all_deployments(since="2026-08-02T10:00:00+00:00")
    filtered_path = client.get_all.await_args.args[0]
    assert "startTime%3A" in filtered_path
    assert "%3BendTime%3A" in filtered_path
