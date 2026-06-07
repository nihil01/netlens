import logging
from collections.abc import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import Settings, get_settings
from app.scanner.service import ScannerService

logger = logging.getLogger(__name__)


class ScannerScheduler:
    def __init__(
        self,
        settings: Settings,
        scanner_factory: Callable[[], ScannerService] = ScannerService.from_settings,
    ) -> None:
        self.settings = settings
        self.scanner_factory = scanner_factory
        self.scheduler = AsyncIOScheduler(timezone="Asia/Baku")

    def start(self) -> None:
        print("Scanner scheduler started")
        if not self.settings.scanner_schedule_enabled:
            logger.info("Scanner daily schedule is disabled")
            return

        trigger = CronTrigger.from_crontab(
            self.settings.scanner_schedule_cron,
            timezone="Asia/Baku",
        )
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
        self.scheduler.start()
        logger.info("Scanner schedule enabled: %s Asia/Baku", self.settings.scanner_schedule_cron)

    async def _run_job(self) -> None:
        scanner = self.scanner_factory()
        result = await scanner.run_scheduled_scan()
        logger.info("Scheduled scanner result: %s", result)

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)


def create_scanner_scheduler() -> ScannerScheduler:
    return ScannerScheduler(get_settings())
