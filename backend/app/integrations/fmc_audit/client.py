"""Read-only FMC Audit and deployment-history REST client."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from app.core.config import Settings
from app.integrations.fmc.client import FmcClient


class FmcAuditClient(FmcClient):
    """Read-only FMC client for audit & deployment data."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)

    # ======================================================================
    # Audit endpoints
    # ======================================================================

    async def get_audit_records(
        self,
        offset: int = 0,
        limit: int = 1000,
        since: str | None = None,
    ) -> dict[str, Any]:
        """Fetch audit records. since = ISO timestamp filter."""
        path = self._platform("/audit/auditrecords")
        params = f"?offset={offset}&limit={limit}&expanded=true"
        return await self.get(f"{path}{params}")

    async def get_audit_record(self, uid: str) -> dict[str, Any]:
        """Fetch single audit record details."""
        return await self.get(self._platform(f"/audit/auditrecords/{uid}"))

    async def get_config_changes(
        self,
        *,
        audit_log_id: str,
        snapshot_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch before/after facts using the two distinct FMC identifiers."""
        query = (
            f"auditLogId={quote(audit_log_id, safe='')}&snapshotId={quote(snapshot_id, safe='')}"
        )
        return await self.get_all(self._platform(f"/audit/configchanges?{query}"))

    async def get_all_audit_records(
        self,
        since: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Paginated fetch of all audit records."""
        path = self._platform("/audit/auditrecords")
        # This FMC platform endpoint does not document a timestamp filter. Do
        # not send a made-up filter that some versions reject with HTTP 400.
        return await self.get_all(path, limit=limit)

    # ======================================================================
    # Deployment endpoints
    # ======================================================================

    async def get_deployments(
        self,
        offset: int = 0,
        limit: int = 1000,
        since: str | None = None,
    ) -> dict[str, Any]:
        """Fetch deployment history."""
        path = self._cfg("/deployment/jobhistories")
        params = f"?offset={offset}&limit={limit}&expanded=true"
        if since:
            time_filter = (
                f"startTime:{_epoch_seconds(since)};"
                f"endTime:{int(datetime.now(UTC).timestamp())}"
            )
            params += f"&filter={quote(time_filter, safe='')}"
        return await self.get(f"{path}{params}")

    async def get_deployment(self, uid: str) -> dict[str, Any]:
        """Fetch single deployment details."""
        return await self.get(self._cfg(f"/deployment/jobhistories/{uid}"))

    async def get_all_deployments(
        self,
        since: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Paginated fetch of all deployments."""
        path = self._cfg("/deployment/jobhistories")
        if since:
            time_filter = (
                f"startTime:{_epoch_seconds(since)};"
                f"endTime:{int(datetime.now(UTC).timestamp())}"
            )
            path += f"?filter={quote(time_filter, safe='')}"
        return await self.get_all(path, limit=limit)


def _epoch_seconds(value: str) -> int:
    """Convert the service ISO watermark to the format expected by FMC."""
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
