import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings, get_settings
from app.integrations.netbox.service import NetBoxService
from app.scanner.pipeline import AdvancedProfilingEngine, PipelineOrchestrator

logger = logging.getLogger(__name__)


class ScannerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._scan_lock = asyncio.Lock()
        self._current_task: asyncio.Task | None = None

    @classmethod
    def from_settings(cls) -> "ScannerService":
        return cls(get_settings())

    def is_running(self) -> bool:
        return self._scan_lock.locked()

    async def run_scheduled_scan(self, trigger: str = "schedule") -> dict[str, Any]:
        if self._scan_lock.locked():
            return {
                "status": "skipped",
                "reason": "scan_already_running",
                "trigger": trigger,
                "scope": self.settings.scanner_default_scope,
                "profile": self.settings.scanner_profile,
                "created_at": datetime.now(UTC).isoformat(),
            }

        async with self._scan_lock:
            started_at = datetime.now(UTC)

            try:
                engine = AdvancedProfilingEngine(
                    credentials=self.settings.scanner_credentials,
                    dataset_path=self.settings.scanner_dataset_path,
                )

                orchestrator = PipelineOrchestrator(engine)
                profiles = await orchestrator.run_pipeline()

                finished_at = datetime.now(UTC)

                return {
                    "status": "completed",
                    "trigger": trigger,
                    "scope": self.settings.scanner_default_scope,
                    "profile": self.settings.scanner_profile,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "hosts_total": len(profiles) if isinstance(profiles, list) else 0,
                }

            except Exception as exc:
                logger.exception("Scheduled scanner failed")

                return {
                    "status": "failed",
                    "trigger": trigger,
                    "scope": self.settings.scanner_default_scope,
                    "profile": self.settings.scanner_profile,
                    "started_at": started_at.isoformat(),
                    "failed_at": datetime.now(UTC).isoformat(),
                    "error": str(exc),
                }

    def start_background_scan(self, trigger: str = "manual") -> dict[str, Any]:
        if self._current_task and not self._current_task.done():
            return {
                "status": "already_running",
                "trigger": trigger,
            }

        self._current_task = asyncio.create_task(
            self.run_scheduled_scan(trigger=trigger)
        )

        return {
            "status": "accepted",
            "trigger": trigger,
            "scope": self.settings.scanner_default_scope,
            "profile": self.settings.scanner_profile,
            "started_at": datetime.now(UTC).isoformat(),
        }