from app.core.config import get_settings
from app.ip_intelligence.schemas import ActivityCounterparty, ActivitySummary


class OpenSearchActivityService:
    def __init__(self, mode: str, index_pattern: str) -> None:
        self.mode = mode
        self.index_pattern = index_pattern

    @classmethod
    def from_settings(cls) -> "OpenSearchActivityService":
        settings = get_settings()
        return cls(mode=settings.opensearch_mode, index_pattern=settings.opensearch_index_pattern)

    async def summarize_ip(self, ip: str, window: str = "24h") -> ActivitySummary:
        if self.mode == "mock":
            return ActivitySummary(
                window=window,
                internal_connections=128,
                external_connections=17,
                security_events=3,
                top_internal_destinations=[
                    ActivityCounterparty(ip="10.10.20.5", port=443, service="HTTPS", count=54),
                    ActivityCounterparty(ip="10.10.30.8", port=53, service="DNS", count=32),
                ],
                top_external_destinations=[
                    ActivityCounterparty(ip="8.8.8.8", port=53, service="DNS", count=9),
                ],
            )

        # Real query templates depend on the actual Check Point/FMC/eStreamer index mappings.
        return ActivitySummary(window=window)
