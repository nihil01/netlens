from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings, get_settings


class ScannerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @classmethod
    def from_settings(cls) -> "ScannerService":
        return cls(get_settings())

    async def run_scheduled_scan(self) -> dict[str, Any]:
        # Placeholder boundary for the real scanner pipeline.
        # Next implementation will call discovery -> ports -> fingerprinting -> persistence.
        started_at = datetime.now(UTC)
        return {
            "status": "accepted",
            "scope": self.settings.scanner_default_scope,
            "profile": self.settings.scanner_profile,
            "started_at": started_at.isoformat(),
        }
