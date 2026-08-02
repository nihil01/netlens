from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.integrations.fmc.service import FmcMonitoringService
from app.integrations.fmc_audit.service import FmcAuditService
from app.integrations.netbox.service import NetBoxService
from app.monitoring.retention import RetentionService
from app.observability.metrics import set_gauge
from app.scanner.service import ScannerService

logger = logging.getLogger(__name__)

_MAX_HISTORY = 50


class JobLockUnavailable(RuntimeError):
    """Another NetLens instance owns this scheduled collection slot."""


class ScannerScheduler:
    def __init__(
        self,
        settings: Settings,
        scanner_factory: Callable[[], ScannerService] | None = None,
        inventory_factory: Callable[[], NetBoxService] | None = None,
        fmc_factory: Callable[[], FmcMonitoringService] | None = None,
        fmc_audit_factory: Callable[[], FmcAuditService] | None = None,
    ) -> None:
        self.settings = settings
        self.scanner_service = scanner_factory() if scanner_factory else ScannerService(settings)
        self.inventory_service = (
            inventory_factory() if inventory_factory else NetBoxService(settings)
        )
        self.fmc_service = fmc_factory() if fmc_factory else FmcMonitoringService(settings)
        self.fmc_audit_service = (
            fmc_audit_factory() if fmc_audit_factory else FmcAuditService(settings)
        )
        self.retention_service = RetentionService(settings)
        self.scheduler = AsyncIOScheduler(timezone="Asia/Baku")
        self.scheduler.add_listener(
            self._record_scheduler_lag,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
        )
        self._history: deque[dict[str, Any]] = deque(maxlen=_MAX_HISTORY)
        self._cron_expression: str = settings.scanner_schedule_cron
        self._enabled: bool = settings.scanner_schedule_enabled
        self._inventory_cron: str = settings.inventory_refresh_cron
        self._inventory_enabled = (
            settings.inventory_refresh_enabled and self.inventory_service._is_configured()
        )
        self._fmc_full_cron: str = settings.fmc_full_scan_cron
        fmc_configured = self.fmc_service.collector.client.configured
        self._fmc_full_enabled = (
            settings.fmc_monitoring_enabled and settings.fmc_full_scan_enabled and fmc_configured
        )
        self._fmc_components_enabled = settings.fmc_monitoring_enabled and fmc_configured
        self._fmc_component_intervals: dict[str, tuple[str, int]] = {
            "discovery": ("minutes", settings.fmc_discovery_refresh_minutes),
            "health": ("seconds", settings.fmc_device_health_refresh_seconds),
            "interfaces": ("minutes", settings.fmc_interface_refresh_minutes),
            "ha": ("seconds", settings.fmc_ha_refresh_seconds),
            "alerts": ("seconds", settings.fmc_alert_refresh_seconds),
            "policy": ("hours", settings.fmc_policy_analysis_refresh_hours),
        }
        self._fmc_vpn_interval_minutes: int = settings.fmc_vpn_refresh_minutes
        self._fmc_vpn_enabled = settings.fmc_vpn_refresh_enabled and fmc_configured
        self._fmc_audit_interval_minutes: int = settings.fmc_audit_interval_minutes
        self._fmc_audit_enabled = (
            settings.fmc_audit_enabled and fmc_configured and bool(settings.database_url)
        )
        self._retention_enabled = settings.retention_enabled and bool(settings.database_url)
        self._retention_cron = settings.retention_cron
        self._last_refresh_time: str | None = None
        self._inventory_operation_lock = asyncio.Lock()
        self._fmc_reset_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        logger.info("Scanner scheduler initializing")
        if not any(
            (
                self._enabled,
                self._inventory_enabled,
                self._fmc_full_enabled,
                self._fmc_components_enabled,
                self._fmc_vpn_enabled,
                self._fmc_audit_enabled,
                self._retention_enabled,
            )
        ):
            logger.info("All scheduled jobs are disabled")
            return

        if self._enabled:
            self._add_scanner_job(self._cron_expression)
        if self._inventory_enabled:
            self._add_inventory_job(self._inventory_cron)
        if self._fmc_full_enabled:
            self._add_fmc_full_job(self._fmc_full_cron)
        if self._fmc_components_enabled:
            for scope, (unit, interval) in self._fmc_component_intervals.items():
                self._add_fmc_component_job(scope, unit, interval)
        if self._fmc_vpn_enabled:
            self._add_fmc_vpn_job(self._fmc_vpn_interval_minutes)
        if self._fmc_audit_enabled:
            self._add_fmc_audit_job(self._fmc_audit_interval_minutes)
        if self._retention_enabled:
            self._add_retention_job(self._retention_cron)
        self.scheduler.start()
        # Run initial refreshes on startup
        if self._inventory_enabled:
            asyncio.create_task(self._run_inventory_job(trigger="startup"))
        if self._fmc_components_enabled:
            asyncio.create_task(self._run_fmc_startup_jobs())
        logger.info(
            "Schedules started: scanner=%s inventory=%s fmc_full=%s "
            "fmc_components=%s fmc_vpn=%sm Asia/Baku",
            self._cron_expression if self._enabled else "disabled",
            self._inventory_cron if self._inventory_enabled else "disabled",
            self._fmc_full_cron if self._fmc_full_enabled else "disabled",
            self._fmc_component_intervals if self._fmc_components_enabled else "disabled",
            self._fmc_vpn_interval_minutes if self._fmc_vpn_enabled else "disabled",
        )

    async def _run_fmc_startup_jobs(self) -> None:
        """Warm discovery and operational VPN state before slower policy analysis."""
        reset_status = await self.fmc_service.get_reset_status()
        if reset_status.get("state") in {"queued", "clearing", "refetching"}:
            await self.fmc_service.set_reset_status(
                "failed",
                started_at=reset_status.get("started_at"),
                completed_scopes=reset_status.get("completed_scopes") or [],
                error="Backend restarted before FMC reset/refetch completed",
            )
        await self._run_fmc_component_job("discovery", trigger="startup")
        if self._fmc_vpn_enabled:
            await self._run_fmc_vpn_job(trigger="startup")
        await self._run_fmc_component_job("policy", trigger="startup")

    def _add_scanner_job(self, cron_expr: str) -> None:
        trigger = CronTrigger.from_crontab(cron_expr, timezone="Asia/Baku")
        self.scheduler.add_job(
            self._run_job,
            trigger=trigger,
            id="daily-scanner",
            name="Daily NetLens scanner",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

    def _add_inventory_job(self, cron_expr: str) -> None:
        trigger = CronTrigger.from_crontab(cron_expr, timezone="Asia/Baku")
        self.scheduler.add_job(
            self._run_inventory_job,
            trigger=trigger,
            id="inventory-refresh",
            name="NetBox inventory cache refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=900,
        )

    def _add_fmc_full_job(self, cron_expr: str) -> None:
        trigger = CronTrigger.from_crontab(cron_expr, timezone="Asia/Baku")
        self.scheduler.add_job(
            self._run_fmc_full_job,
            trigger=trigger,
            id="fmc-full-scan",
            name="FMC full device scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

    def _add_fmc_vpn_job(self, interval_minutes: int) -> None:
        from apscheduler.triggers.interval import IntervalTrigger

        trigger = IntervalTrigger(minutes=interval_minutes, jitter=10, timezone="Asia/Baku")
        self.scheduler.add_job(
            self._run_fmc_vpn_job,
            trigger=trigger,
            id="fmc-vpn-refresh",
            name="FMC VPN tunnel status refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=120,
        )

    def _add_fmc_component_job(self, scope: str, unit: str, interval: int) -> None:
        from apscheduler.triggers.interval import IntervalTrigger

        arguments = {unit: max(1, interval), "jitter": 10, "timezone": "Asia/Baku"}
        self.scheduler.add_job(
            self._run_fmc_component_job,
            trigger=IntervalTrigger(**arguments),
            args=[scope],
            id=f"fmc-{scope}",
            name=f"FMC {scope} collector",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=120,
        )

    def _add_fmc_audit_job(self, interval_minutes: int) -> None:
        from apscheduler.triggers.interval import IntervalTrigger

        trigger = IntervalTrigger(minutes=interval_minutes, timezone="Asia/Baku")
        self.scheduler.add_job(
            self._run_fmc_audit_job,
            trigger=trigger,
            id="fmc-audit-poll",
            name="FMC Audit & Change Intelligence poll",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=120,
        )

    def _add_retention_job(self, cron_expr: str) -> None:
        trigger = CronTrigger.from_crontab(cron_expr, timezone="Asia/Baku")
        self.scheduler.add_job(
            self._run_retention_job,
            trigger=trigger,
            id="history-retention",
            name="NetLens history retention",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

    async def _run_job(self) -> None:
        run_record: dict[str, Any] = {
            "job": "scanner",
            "trigger": "schedule",
            "started_at": datetime.now(UTC).isoformat(),
            "cron": self._cron_expression,
        }

        try:
            result = await self.scanner_service.run_scheduled_scan()
            run_record["status"] = result.get("status", "unknown")
            run_record["finished_at"] = datetime.now(UTC).isoformat()
            run_record["hosts_total"] = result.get("hosts_total", 0)
            logger.info("Scheduled scanner result: %s", result)
        except Exception as exc:
            run_record["status"] = "failed"
            run_record["error"] = str(exc)
            run_record["finished_at"] = datetime.now(UTC).isoformat()
            logger.exception("Scheduled scanner failed")

        self._history.append(run_record)

    async def _run_inventory_job(self, trigger: str = "schedule") -> None:
        run_record: dict[str, Any] = {
            "job": "inventory-refresh",
            "trigger": trigger,
            "started_at": datetime.now(UTC).isoformat(),
            "cron": self._inventory_cron,
        }

        async with self._inventory_operation_lock:
            try:
                inventory = await self.inventory_service.refresh_inventory()
                run_record["status"] = inventory.status.status
                run_record["finished_at"] = datetime.now(UTC).isoformat()
                run_record["devices_total"] = len(inventory.devices)
                self._last_refresh_time = run_record["finished_at"]
                if inventory.status.message:
                    run_record["message"] = inventory.status.message
                logger.info("Inventory cache refresh result: %s", run_record)
            except Exception as exc:
                run_record["status"] = "failed"
                run_record["error"] = str(exc)
                run_record["finished_at"] = datetime.now(UTC).isoformat()
                logger.exception("Inventory cache refresh failed")

        self._history.append(run_record)

    async def _run_fmc_full_job(self, trigger: str = "schedule") -> None:
        run_record: dict[str, Any] = {
            "job": "fmc-full-scan",
            "trigger": trigger,
            "started_at": datetime.now(UTC).isoformat(),
            "cron": self._fmc_full_cron,
        }

        try:
            dashboard = await self._execute_exclusive(
                "fmc:api", self.fmc_service.refresh_full_scan
            )
            run_record["status"] = "ok"
            run_record["finished_at"] = datetime.now(UTC).isoformat()
            run_record["devices_total"] = dashboard.total_devices
            run_record["devices_connected"] = dashboard.devices_connected
            logger.info("FMC full scan result: %s", run_record)
        except JobLockUnavailable:
            run_record["status"] = "skipped_locked"
            run_record["finished_at"] = datetime.now(UTC).isoformat()
        except Exception as exc:
            run_record["status"] = "failed"
            run_record["error"] = str(exc)
            run_record["finished_at"] = datetime.now(UTC).isoformat()
            logger.exception("FMC full scan failed")

        self._history.append(run_record)

    async def _run_fmc_component_job(self, scope: str, trigger: str = "schedule") -> None:
        run_record: dict[str, Any] = {
            "job": f"fmc-{scope}",
            "trigger": trigger,
            "started_at": datetime.now(UTC).isoformat(),
            "interval": self._fmc_component_intervals.get(scope),
        }
        operations = {
            "discovery": self.fmc_service.refresh_discovery,
            "health": self.fmc_service.refresh_device_health,
            "interfaces": self.fmc_service.refresh_interfaces,
            "ha": self.fmc_service.refresh_ha,
            "alerts": self.fmc_service.refresh_alerts,
            "policy": self.fmc_service.refresh_policy_analysis,
        }
        try:
            # Health feeds every device chart. Unlike slower auxiliary collectors,
            # it must queue behind an active FMC job instead of losing a 5-minute
            # sample when schedules overlap.
            dashboard = await self._execute_exclusive(
                "fmc:api", operations[scope], wait=scope == "health"
            )
            source = self.fmc_service._scope_freshness(scope)[0]
            freshness = next(
                (item for item in dashboard.source_freshness if item.source == source), None
            )
            result_status = (
                "failed"
                if freshness and freshness.state.value == "ERROR"
                else "degraded"
                if freshness and freshness.state.value in {"DEGRADED", "STALE"}
                else "ok"
            )
            run_record.update(
                {
                    "status": result_status,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "records": len(dashboard.ha_pairs)
                    if scope == "ha"
                    else dashboard.policy_analysis.get("total_policies", 0)
                    if scope == "policy"
                    else dashboard.total_devices,
                }
            )
            logger.info("FMC %s collector result: %s", scope, run_record)
        except JobLockUnavailable:
            run_record.update(
                {
                    "status": "skipped_locked",
                    "finished_at": datetime.now(UTC).isoformat(),
                }
            )
        except Exception as exc:
            run_record.update(
                {
                    "status": "failed",
                    "error": str(exc),
                    "finished_at": datetime.now(UTC).isoformat(),
                }
            )
            logger.exception("FMC %s collector failed", scope)
        self._history.append(run_record)

    async def _run_fmc_vpn_job(self, trigger: str = "schedule") -> None:
        run_record: dict[str, Any] = {
            "job": "fmc-vpn-refresh",
            "trigger": trigger,
            "started_at": datetime.now(UTC).isoformat(),
            "interval_minutes": self._fmc_vpn_interval_minutes,
        }

        try:
            dashboard = await self._execute_exclusive(
                "fmc:api", self.fmc_service.refresh_vpn_status, wait=True
            )
            freshness = next(
                (item for item in dashboard.source_freshness if item.source == "fmc_vpn"),
                None,
            )
            run_record["status"] = (
                "failed"
                if freshness and freshness.state.value == "ERROR"
                else "degraded"
                if freshness and freshness.state.value in {"DEGRADED", "STALE"}
                else "ok"
            )
            run_record["finished_at"] = datetime.now(UTC).isoformat()
            run_record["tunnel_up"] = dashboard.tunnel_up
            run_record["tunnel_down"] = dashboard.tunnel_down
            logger.info("FMC VPN refresh result: %s", run_record)
        except JobLockUnavailable:
            run_record["status"] = "skipped_locked"
            run_record["finished_at"] = datetime.now(UTC).isoformat()
        except Exception as exc:
            run_record["status"] = "failed"
            run_record["error"] = str(exc)
            run_record["finished_at"] = datetime.now(UTC).isoformat()
            logger.exception("FMC VPN refresh failed")

        self._history.append(run_record)

    async def _run_fmc_audit_job(self, trigger: str = "schedule") -> None:
        run_record: dict[str, Any] = {
            "job": "fmc-audit-poll",
            "trigger": trigger,
            "started_at": datetime.now(UTC).isoformat(),
            "interval_minutes": self._fmc_audit_interval_minutes,
        }

        try:
            result = await self._execute_exclusive("fmc:api", self.fmc_audit_service.refresh)
            run_record["status"] = result.get("status", "ok")
            run_record["finished_at"] = datetime.now(UTC).isoformat()
            run_record["new_records"] = result.get("new_records", 0)
            run_record["new_deployments"] = result.get("new_deployments", 0)
            logger.info("FMC audit poll result: %s", run_record)
        except JobLockUnavailable:
            run_record["status"] = "skipped_locked"
            run_record["finished_at"] = datetime.now(UTC).isoformat()
        except Exception as exc:
            run_record["status"] = "failed"
            run_record["error"] = str(exc)
            run_record["finished_at"] = datetime.now(UTC).isoformat()
            logger.exception("FMC audit poll failed")

        self._history.append(run_record)

    async def _run_retention_job(self, trigger: str = "schedule") -> None:
        run_record: dict[str, Any] = {
            "job": "history-retention",
            "trigger": trigger,
            "started_at": datetime.now(UTC).isoformat(),
            "cron": self._retention_cron,
        }
        try:
            result = await self._execute_exclusive("history:retention", self.retention_service.run)
            run_record.update(
                {
                    "status": "ok",
                    "finished_at": datetime.now(UTC).isoformat(),
                    "deleted": result["deleted"],
                }
            )
        except JobLockUnavailable:
            run_record["status"] = "skipped_locked"
            run_record["finished_at"] = datetime.now(UTC).isoformat()
        except Exception as exc:
            run_record["status"] = "failed"
            run_record["error"] = str(exc)
            run_record["finished_at"] = datetime.now(UTC).isoformat()
            logger.exception("History retention failed")
        self._history.append(run_record)

    def update_cron(self, cron_expr: str) -> dict[str, Any]:
        self._cron_expression = cron_expr

        if self.scheduler.running:
            try:
                self.scheduler.remove_job("daily-scanner")
            except Exception:
                pass

            if self._enabled:
                self._add_scanner_job(cron_expr)

        return self.get_status()

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        self._enabled = enabled

        if enabled and not self.scheduler.running:
            self._add_scanner_job(self._cron_expression)
            if self._inventory_enabled:
                self._add_inventory_job(self._inventory_cron)
            self.scheduler.start()
        elif enabled and self.scheduler.running:
            self._add_scanner_job(self._cron_expression)
        elif not enabled and self.scheduler.running:
            try:
                self.scheduler.remove_job("daily-scanner")
            except Exception:
                pass

        return self.get_status()

    def trigger_now(self) -> dict[str, Any]:
        if self.scanner_service.is_running():
            return {"status": "already_running"}

        asyncio.create_task(self._run_manual_job())
        return {
            "status": "accepted",
            "trigger": "manual",
            "started_at": datetime.now(UTC).isoformat(),
        }

    def trigger_inventory_refresh(self) -> dict[str, Any]:
        """Manually trigger an immediate inventory cache refresh."""
        asyncio.create_task(self._run_inventory_job(trigger="manual"))
        return {
            "status": "accepted",
            "trigger": "manual",
            "started_at": datetime.now(UTC).isoformat(),
        }

    async def reset_inventory_and_refresh(self) -> dict[str, Any]:
        """Clear every NetBox cache entry, then wait for a fresh inventory."""
        async with self._inventory_operation_lock:
            deleted = await self.inventory_service.clear_cache()
            inventory = await self.inventory_service.refresh_inventory()
            finished_at = datetime.now(UTC).isoformat()
            self._last_refresh_time = finished_at
            result = {
                "status": inventory.status.status,
                "cache_keys_deleted": deleted,
                "devices_total": len(inventory.devices),
                "finished_at": finished_at,
            }
            if inventory.status.message:
                result["message"] = inventory.status.message
            self._history.append(
                {"job": "inventory-reset", "trigger": "manual", **result}
            )
            return result

    async def trigger_fmc_reset(self) -> dict[str, Any]:
        """Queue one destructive monitoring reset followed by a complete refetch."""
        if not self.fmc_service.collector.client.configured:
            return {"status": "not_configured"}
        if self._fmc_reset_task and not self._fmc_reset_task.done():
            return {"status": "already_running"}
        started_at = datetime.now(UTC).isoformat()
        await self.fmc_service.set_reset_status("queued", started_at=started_at)
        self._fmc_reset_task = asyncio.create_task(self._run_fmc_reset_job())
        return {
            "status": "accepted",
            "trigger": "manual",
            "started_at": started_at,
        }

    async def _run_fmc_reset_job(self) -> None:
        run_record: dict[str, Any] = {
            "job": "fmc-reset",
            "trigger": "manual",
            "started_at": datetime.now(UTC).isoformat(),
        }

        async def reset_and_refetch() -> dict[str, Any]:
            await self.fmc_service.set_reset_status(
                "clearing", started_at=run_record["started_at"]
            )
            reset_result = await self.fmc_service.clear_monitoring_data()
            operations = (
                ("discovery", self.fmc_service.refresh_discovery),
                ("health", self.fmc_service.refresh_device_health),
                ("interfaces", self.fmc_service.refresh_interfaces),
                ("ha", self.fmc_service.refresh_ha),
                ("alerts", self.fmc_service.refresh_alerts),
                ("policy", self.fmc_service.refresh_policy_analysis),
            )
            completed_scopes: list[str] = []
            for scope, operation in operations:
                await operation()
                completed_scopes.append(scope)
                await self.fmc_service.set_reset_status(
                    "refetching",
                    started_at=run_record["started_at"],
                    completed_scopes=completed_scopes,
                )
            await self.fmc_service.refresh_vpn_status()
            completed_scopes.append("vpn")
            return {**reset_result, "completed_scopes": completed_scopes}

        try:
            result = await self._execute_exclusive("fmc:api", reset_and_refetch, wait=True)
            run_record.update(
                status="completed",
                finished_at=datetime.now(UTC).isoformat(),
                **result,
            )
            logger.warning("FMC reset and refetch completed: %s", run_record)
            await self.fmc_service.set_reset_status(
                "completed",
                started_at=run_record["started_at"],
                completed_scopes=result["completed_scopes"],
            )
        except JobLockUnavailable:
            run_record.update(
                status="skipped_locked",
                finished_at=datetime.now(UTC).isoformat(),
            )
        except Exception as exc:
            run_record.update(
                status="failed",
                error=str(exc),
                finished_at=datetime.now(UTC).isoformat(),
            )
            logger.exception("FMC reset and refetch failed")
            await self.fmc_service.set_reset_status(
                "failed", started_at=run_record["started_at"], error=str(exc)
            )
        finally:
            self._history.append(run_record)

    def get_inventory_status(self) -> dict[str, Any]:
        """Return inventory refresh status including last refresh time."""
        next_run = None
        if self.scheduler.running and self._inventory_enabled:
            job = self.scheduler.get_job("inventory-refresh")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()

        return {
            "enabled": self._inventory_enabled,
            "cron": self._inventory_cron,
            "next_run": next_run,
            "last_refresh_at": self._last_refresh_time,
        }

    async def _run_manual_job(self) -> None:
        run_record: dict[str, Any] = {
            "job": "scanner",
            "trigger": "manual",
            "started_at": datetime.now(UTC).isoformat(),
            "cron": self._cron_expression,
        }

        try:
            result = await self.scanner_service.run_scheduled_scan(trigger="manual")
            run_record["status"] = result.get("status", "unknown")
            run_record["finished_at"] = datetime.now(UTC).isoformat()
            run_record["hosts_total"] = result.get("hosts_total", 0)
        except Exception as exc:
            run_record["status"] = "failed"
            run_record["error"] = str(exc)
            run_record["finished_at"] = datetime.now(UTC).isoformat()

        self._history.append(run_record)

    def get_status(self) -> dict[str, Any]:
        next_run = None
        if self.scheduler.running and self._enabled:
            job = self.scheduler.get_job("daily-scanner")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()

        inventory_next_run = None
        if self.scheduler.running and self._inventory_enabled:
            inventory_job = self.scheduler.get_job("inventory-refresh")
            if inventory_job and inventory_job.next_run_time:
                inventory_next_run = inventory_job.next_run_time.isoformat()

        fmc_full_next_run = None
        if self.scheduler.running and self._fmc_full_enabled:
            fmc_job = self.scheduler.get_job("fmc-full-scan")
            if fmc_job and fmc_job.next_run_time:
                fmc_full_next_run = fmc_job.next_run_time.isoformat()

        fmc_vpn_next_run = None
        if self.scheduler.running and self._fmc_vpn_enabled:
            vpn_job = self.scheduler.get_job("fmc-vpn-refresh")
            if vpn_job and vpn_job.next_run_time:
                fmc_vpn_next_run = vpn_job.next_run_time.isoformat()

        fmc_audit_next_run = None
        if self.scheduler.running and self._fmc_audit_enabled:
            audit_job = self.scheduler.get_job("fmc-audit-poll")
            if audit_job and audit_job.next_run_time:
                fmc_audit_next_run = audit_job.next_run_time.isoformat()

        component_status = {}
        for scope, (unit, interval) in self._fmc_component_intervals.items():
            job = self.scheduler.get_job(f"fmc-{scope}") if self.scheduler.running else None
            component_status[scope] = {
                "enabled": self._fmc_components_enabled,
                "interval": {"unit": unit, "value": interval},
                "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
            }

        retention_job = (
            self.scheduler.get_job("history-retention") if self.scheduler.running else None
        )

        return {
            "enabled": self._enabled,
            "cron": self._cron_expression,
            "timezone": "Asia/Baku",
            "running": self.scheduler.running,
            "next_run": next_run,
            "inventory": {
                "enabled": self._inventory_enabled,
                "cron": self._inventory_cron,
                "next_run": inventory_next_run,
            },
            "fmc": {
                "collectors": component_status,
                "full_scan": {
                    "enabled": self._fmc_full_enabled,
                    "cron": self._fmc_full_cron,
                    "next_run": fmc_full_next_run,
                },
                "vpn_refresh": {
                    "enabled": self._fmc_vpn_enabled,
                    "interval_minutes": self._fmc_vpn_interval_minutes,
                    "next_run": fmc_vpn_next_run,
                },
                "audit": {
                    "enabled": self._fmc_audit_enabled,
                    "interval_minutes": self._fmc_audit_interval_minutes,
                    "next_run": fmc_audit_next_run,
                },
            },
            "retention": {
                "enabled": self._retention_enabled,
                "cron": self._retention_cron,
                "next_run": retention_job.next_run_time.isoformat()
                if retention_job and retention_job.next_run_time
                else None,
            },
        }

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        items = list(self._history)
        return items[-limit:]

    async def _execute_exclusive(
        self, name: str, operation: Callable, *, wait: bool = False
    ) -> Any:
        async with self._job_lock(name, wait=wait) as acquired:
            if not acquired:
                raise JobLockUnavailable(name)
            return await operation()

    @asynccontextmanager
    async def _job_lock(self, name: str, *, wait: bool = False):
        """Use a PostgreSQL advisory lock when multiple backend replicas exist."""
        if not self.settings.database_url:
            yield True
            return
        from app.db import session_scope

        lock_id = int.from_bytes(
            hashlib.blake2b(name.encode(), digest_size=8).digest(),
            byteorder="big",
            signed=True,
        )
        async with session_scope() as session:
            if wait:
                await session.execute(
                    text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": lock_id}
                )
                acquired = True
            else:
                acquired = bool(
                    await session.scalar(
                        text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}
                    )
                )
            try:
                yield acquired
            finally:
                if acquired:
                    await session.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id}
                    )

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    @staticmethod
    def _record_scheduler_lag(event: Any) -> None:
        scheduled = getattr(event, "scheduled_run_time", None)
        if scheduled is not None:
            set_gauge(
                "scheduler_lag_seconds",
                max(0.0, (datetime.now(UTC) - scheduled).total_seconds()),
            )


def create_scanner_scheduler() -> ScannerScheduler:
    return ScannerScheduler(get_settings())
