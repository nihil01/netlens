"""FMC Audit Collector — fetches audit records & deployments, normalizes data."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings
from app.integrations.fmc_audit.client import FmcAuditClient
from app.integrations.fmc_audit.schemas import AuditRecordDto, DeploymentDto

logger = logging.getLogger(__name__)

# Object types that are high-risk for changes
HIGH_RISK_TYPES = frozenset(
    {
        "AccessPolicy",
        "ACLPolicy",
        "FTDS2SVPN",
        "NatPolicy",
        "RoutingProtocol",
        "PlatformSettings",
        "DeviceGroup",
        "HealthPolicy",
        "IntrusionPolicy",
        "FilePolicy",
        "DNSPolicy",
        "IdentityPolicy",
    }
)

# Fields that are critical when changed
CRITICAL_FIELDS = frozenset(
    {
        "action",
        "networks",
        "hosts",
        "ports",
        "securityZone",
        "route",
        "destinationNetworks",
        "sourceNetworks",
        "enabled",
        "logBegin",
        "logEnd",
    }
)


class FmcAuditCollector:
    """Read-only collector for FMC audit trail & deployment history."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = FmcAuditClient(self.settings)

    @classmethod
    def from_settings(cls) -> FmcAuditCollector:
        return cls(get_settings())

    async def collect_audit_records(self, since: str | None = None) -> list[AuditRecordDto]:
        """Fetch and normalize audit records from FMC."""
        if not self.client.configured:
            return []

        try:
            await self.client.authenticate()
        except Exception as exc:
            logger.exception("FMC auth failed for audit: %s", exc)
            return []

        try:
            raw_records = await self.client.get_all_audit_records(since=since)
        except Exception as exc:
            logger.exception("FMC audit records fetch failed: %s", exc)
            return []

        if since:
            watermark = self._parse_timestamp(since)
            if watermark:
                raw_records = [
                    raw
                    for raw in raw_records
                    if (self._raw_audit_timestamp(raw) is None)
                    or self._raw_audit_timestamp(raw) >= watermark
                ]

        enriched_records = await self._enrich_config_changes(raw_records)
        normalized = []
        for raw in enriched_records:
            try:
                dto = self._normalize_audit_record(raw)
                normalized.append(dto)
            except Exception as exc:
                logger.warning(
                    "Failed to normalize audit record id=%s audit_id=%s: %s",
                    raw.get("id"),
                    raw.get("auditId"),
                    exc,
                )
                continue

        logger.info("FMC audit: collected %d records (since=%s)", len(normalized), since)
        return normalized

    async def collect_deployments(self, since: str | None = None) -> list[DeploymentDto]:
        """Fetch and normalize deployment history from FMC."""
        if not self.client.configured:
            return []

        try:
            await self.client.authenticate()
        except Exception as exc:
            logger.exception("FMC auth failed for deployments: %s", exc)
            return []

        try:
            raw_deps = await self.client.get_all_deployments(since=since)
        except Exception as exc:
            logger.exception("FMC deployments fetch failed: %s", exc)
            return []

        normalized = []
        for raw in raw_deps:
            try:
                dto = self._normalize_deployment(raw)
                normalized.append(dto)
            except Exception as exc:
                logger.warning("Failed to normalize deployment id=%s: %s", raw.get("id"), exc)
                continue

        logger.info("FMC audit: collected %d deployments", len(normalized))
        return normalized

    def _normalize_audit_record(self, raw: dict) -> AuditRecordDto:
        """Normalize a raw FMC audit record into AuditRecordDto."""
        original_raw = raw
        record_id = _string_or_none(raw.get("id") or raw.get("recordId"))
        audit_id = _string_or_none(raw.get("auditId") or raw.get("auditLogId"))
        snapshot_id = _string_or_none(raw.get("snapshotId"))
        fmc_id = record_id or audit_id or self._content_identifier(original_raw)
        raw = _mask_secrets(raw)
        timestamp = self._parse_timestamp(
            raw.get("timestamp") or raw.get("time") or raw.get("startTime")
        )
        user_name = raw.get("userName") or raw.get("username") or raw.get("user")
        user_id = raw.get("userId") or raw.get("user_id")
        source_ip = raw.get("sourceIp") or raw.get("source_ip") or raw.get("clientAddress")
        source = raw.get("source")
        if source_ip is None and isinstance(source, str):
            source_ip = source

        config_changes = raw.get("_netlensConfigChanges") or raw.get("configChanges") or []
        config_changes = config_changes if isinstance(config_changes, list) else []
        first_change = config_changes[0] if len(config_changes) == 1 else {}

        action = (raw.get("action") or first_change.get("action") or "UNKNOWN").upper()
        if action not in ("ADD", "UPDATE", "DELETE", "NOCHANGE"):
            action = "UNKNOWN"

        # Object info
        obj = raw.get("object") if isinstance(raw.get("object"), dict) else {}
        object_type = obj.get("type") or raw.get("objectType") or first_change.get("entityType")
        object_name = obj.get("name") or raw.get("objectName") or first_change.get("entityName")
        object_id = (
            obj.get("id")
            or raw.get("objectId")
            or raw.get("entityUUID")
            or raw.get("entityId")
            or first_change.get("entityUUID")
            or first_change.get("entityId")
        )

        # Parent info
        parent = raw.get("parent") or {}
        parent_type = parent.get("type") or raw.get("parentType")
        parent_name = parent.get("name") or raw.get("parentName")
        parent_id = (
            parent.get("id")
            or raw.get("parentId")
            or raw.get("parentUUID")
            or first_change.get("parentUUID")
        )

        # Before/After snapshots
        before_json = raw.get("before") or raw.get("previousValue")
        after_json = raw.get("after") or raw.get("currentValue") or raw.get("value")

        values_added = _list_alias(raw, "valuesAdded", "valueAdded")
        values_deleted = _list_alias(raw, "valuesDeleted", "valueDeleted")
        values_updated = _list_alias(raw, "valuesUpdated", "valueUpdated")
        for change in config_changes:
            if not isinstance(change, dict):
                continue
            values_added.extend(_list_alias(change, "valuesAdded", "valueAdded"))
            values_deleted.extend(_list_alias(change, "valuesDeleted", "valueDeleted"))
            values_updated.extend(_list_alias(change, "valuesUpdated", "valueUpdated"))

        if before_json is None and after_json is None:
            before_json, after_json = self._snapshots_from_values(
                values_added, values_deleted, values_updated
            )

        # Changed fields
        changed_fields = raw.get("changedFields") or raw.get("fieldsChanged") or []
        if not changed_fields and before_json and after_json:
            changed_fields = self._compute_changed_fields(before_json, after_json)

        # References
        refs_added = _list_alias(raw, "refsAdded", "addedReferences", "referencesAdded")
        refs_removed = _list_alias(raw, "refsRemoved", "removedReferences", "referencesDeleted")
        for change in config_changes:
            if isinstance(change, dict):
                refs_added.extend(_list_alias(change, "referencesAdded"))
                refs_removed.extend(_list_alias(change, "referencesDeleted"))

        # Deployment link
        deployment_id = raw.get("deploymentId") or raw.get("deployment_id")
        deployed = deployment_id is not None
        deploy_success = raw.get("deploySuccess")

        return AuditRecordDto(
            fmc_id=str(fmc_id),
            audit_id=audit_id,
            record_id=record_id,
            snapshot_id=snapshot_id,
            timestamp=timestamp,
            local_timestamp=timestamp.astimezone(ZoneInfo("Asia/Baku")) if timestamp else None,
            user_name=user_name,
            user_id=user_id,
            source_ip=source_ip,
            source=source,
            subsystem=raw.get("subSystem") or raw.get("subsystem"),
            message=raw.get("message"),
            description=raw.get("description"),
            action=action,
            object_type=object_type,
            object_name=object_name,
            object_id=object_id,
            parent_type=parent_type,
            parent_name=parent_name,
            parent_id=parent_id,
            before_json=before_json if isinstance(before_json, dict) else None,
            after_json=after_json if isinstance(after_json, dict) else None,
            changed_fields=changed_fields if isinstance(changed_fields, list) else [],
            refs_added=refs_added if isinstance(refs_added, list) else [],
            refs_removed=refs_removed if isinstance(refs_removed, list) else [],
            values_added=values_added,
            values_deleted=values_deleted,
            values_updated=values_updated,
            config_changes=config_changes,
            raw_json={key: value for key, value in raw.items() if key != "_netlensConfigChanges"},
            normalization_notes=self._normalization_notes(raw, config_changes),
            deployed=deployed,
            deploy_success=deploy_success,
            deployment_id=deployment_id,
        )

    def _normalize_deployment(self, raw: dict) -> DeploymentDto:
        """Normalize a raw FMC deployment into DeploymentDto."""
        fmc_id = raw.get("id", "")
        name = raw.get("jobName") or raw.get("name")
        status = (raw.get("jobStatus") or raw.get("status") or "UNKNOWN").upper()

        started_at = self._parse_timestamp(raw.get("startTime") or raw.get("startedAt"))
        completed_at = self._parse_timestamp(raw.get("endTime") or raw.get("completedAt"))

        triggered_by = raw.get("triggeredBy") or raw.get("userName") or raw.get("user")

        devices = raw.get("deviceList") or raw.get("deployedDevices") or raw.get("devices") or []
        device_count = len(devices)
        success_count = sum(
            1
            for device in devices
            if (device.get("deploymentStatus") or device.get("status") or "").upper()
            in ("SUCCESS", "SUCCEEDED")
        )
        failed_count = sum(
            1
            for device in devices
            if (device.get("deploymentStatus") or device.get("status") or "").upper()
            in ("FAILED", "ERROR")
        )

        return DeploymentDto(
            fmc_id=str(fmc_id),
            name=name,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            triggered_by=triggered_by,
            device_count=device_count,
            success_count=success_count,
            failed_count=failed_count,
            devices=devices if isinstance(devices, list) else [],
            raw_json=raw,
        )

    async def _enrich_config_changes(self, records: list[dict]) -> list[dict]:
        semaphore = asyncio.Semaphore(3)

        async def enrich(raw: dict) -> dict:
            audit_id = _string_or_none(raw.get("auditId") or raw.get("auditLogId"))
            snapshot_id = _string_or_none(raw.get("snapshotId"))
            if not audit_id or not snapshot_id:
                return raw
            try:
                async with semaphore:
                    changes = await self.client.get_config_changes(
                        audit_log_id=audit_id,
                        snapshot_id=snapshot_id,
                    )
                return {**raw, "_netlensConfigChanges": changes}
            except Exception as exc:
                logger.warning(
                    "FMC config changes fetch failed audit_id=%s snapshot_id=%s: %s",
                    audit_id,
                    snapshot_id,
                    exc,
                )
                return raw

        return list(await asyncio.gather(*(enrich(raw) for raw in records)))

    @staticmethod
    def _snapshots_from_values(
        added: list[dict], deleted: list[dict], updated: list[dict]
    ) -> tuple[dict | None, dict | None]:
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        for value in updated:
            if not isinstance(value, dict):
                continue
            field = value.get("fieldName") or value.get("name")
            if field:
                before[str(field)] = value.get("oldValue")
                after[str(field)] = value.get("newValue")
        for value in added:
            if isinstance(value, dict):
                field = value.get("fieldName") or value.get("name")
                if field:
                    after[str(field)] = value.get("value") or value.get("newValue")
        for value in deleted:
            if isinstance(value, dict):
                field = value.get("fieldName") or value.get("name")
                if field:
                    before[str(field)] = value.get("value") or value.get("oldValue")
        return before or None, after or None

    @staticmethod
    def _normalization_notes(raw: dict, changes: list[dict]) -> list[str]:
        notes = []
        if raw.get("entityId") and not raw.get("entityUUID"):
            notes.append("entityId normalized as entity UUID alias")
        if changes:
            notes.append("config changes fetched using auditId and snapshotId")
        return notes

    @staticmethod
    def _content_identifier(raw: dict) -> str:
        canonical = json.dumps(raw, sort_keys=True, default=str, separators=(",", ":"))
        return f"content:{hashlib.sha256(canonical.encode()).hexdigest()}"

    def _compute_changed_fields(self, before: dict, after: dict) -> list[str]:
        """Compute which fields changed between before and after."""
        changed = []
        all_keys = set(before.keys()) | set(after.keys())
        for key in all_keys:
            b_val = before.get(key)
            a_val = after.get(key)
            if b_val != a_val:
                changed.append(key)
        return changed

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            seconds = float(value)
            if seconds > 10_000_000_000:
                seconds /= 1000
            return datetime.fromtimestamp(seconds, tz=UTC)
        if isinstance(value, str) and value.strip().isdigit():
            return FmcAuditCollector._parse_timestamp(int(value.strip()))
        try:
            from dateutil.parser import parse

            return parse(str(value))
        except Exception:
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except Exception:
                return None

    @classmethod
    def _raw_audit_timestamp(cls, raw: dict) -> datetime | None:
        return cls._parse_timestamp(raw.get("timestamp") or raw.get("time") or raw.get("startTime"))


def _list_alias(raw: dict, *names: str) -> list[dict]:
    for name in names:
        value = raw.get(name)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _string_or_none(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


_SECRET_KEY_PARTS = ("authorization", "cookie", "password", "passwd", "secret", "token")
_INLINE_SECRET = re.compile(
    r"(?i)\b(authorization|cookie|password|passwd|secret|token)\b(\s*[:=]\s*)([^\s,;]+)"
)


def _mask_secrets(value: Any) -> Any:
    """Mask credentials in raw audit facts and before/after values."""
    if isinstance(value, list):
        return [_mask_secrets(item) for item in value]
    if isinstance(value, dict):
        field_name = str(value.get("fieldName") or value.get("name") or "").casefold()
        sensitive_field = any(part in field_name for part in _SECRET_KEY_PARTS)
        masked: dict[str, Any] = {}
        for key, item in value.items():
            key_sensitive = any(part in str(key).casefold() for part in _SECRET_KEY_PARTS)
            value_slot = key in {"oldValue", "newValue", "value"}
            masked[key] = (
                "***" if key_sensitive or (sensitive_field and value_slot) else _mask_secrets(item)
            )
        return masked
    if isinstance(value, str):
        return _INLINE_SECRET.sub(r"\1\2***", value)
    return value
