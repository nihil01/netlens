from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import Settings, get_settings
from app.scanner.service import ScannerService

logger = logging.getLogger(__name__)

_MAX_HISTORY = 50


class ScannerScheduler:
    def __init__(
        self,
        settings: Settings,
        scanner_factory: Callable[[], ScannerService] = ScannerService.from_settings,
    ) -> None:
        self.settings = settings
        self.scanner_factory = scanner_factory
        self.scheduler = AsyncIOScheduler(timezone="Asia/Baku")
        self._history: deque[dict[str, Any]] = deque(maxlen=_MAX_HISTORY)
        self._cron_expression: str = settings.scanner_schedule_cron
        self._enabled: bool = settings.scanner_schedule_enabled

    def start(self) -> None:
        logger.info("Scanner scheduler initializing")
        if not self._enabled:
            logger.info("Scanner daily schedule is disabled")
            return

        self._add_job(self._cron_expression)
        self.scheduler.start()
        logger.info("Scanner schedule enabled: %s Asia/Baku", self._cron_expression)

    def _add_job(self, cron_expr: str) -> None:
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

    async def _run_job(self) -> None:
        run_record: dict[str, Any] = {
            "trigger": "schedule",
            "started_at": datetime.now(UTC).isoformat(),
            "cron": self._cron_expression,
        }

        try:
            scanner = self.scanner_factory()
            result = await scanner.run_scheduled_scan()
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

    def update_cron(self, cron_expr: str) -> dict[str, Any]:
        self._cron_expression = cron_expr

        if self.scheduler.running:
            try:
                self.scheduler.remove_job("daily-scanner")
            except Exception:
                pass

            if self._enabled:
                self._add_job(cron_expr)

        return self.get_status()

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        self._enabled = enabled

        if enabled and not self.scheduler.running:
            self._add_job(self._cron_expression)
            self.scheduler.start()
        elif not enabled and self.scheduler.running:
            try:
                self.scheduler.remove_job("daily-scanner")
            except Exception:
                pass

        return self.get_status()

    def trigger_now(self) -> dict[str, Any]:
        import asyncio

        if self._scan_lock.locked() if hasattr(self, "_scan_lock") else False:
            return {"status": "already_running"}

        asyncio.create_task(self._run_manual_job())
        return {
            "status": "accepted",
            "trigger": "manual",
            "started_at": datetime.now(UTC).isoformat(),
        }

    async def _run_manual_job(self) -> None:
        run_record: dict[str, Any] = {
            "trigger": "manual",
            "started_at": datetime.now(UTC).isoformat(),
            "cron": self._cron_expression,
        }

        try:
            scanner = self.scanner_factory()
            result = await scanner.run_scheduled_scan(trigger="manual")
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

        return {
            "enabled": self._enabled,
            "cron": self._cron_expression,
            "timezone": "Asia/Baku",
            "running": self.scheduler.running,
            "next_run": next_run,
        }

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        items = list(self._history)
        return items[-limit:]

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)


def create_scanner_scheduler() -> ScannerScheduler:
    return ScannerScheduler(get_settings())
