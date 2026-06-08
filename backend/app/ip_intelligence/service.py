import ipaddress

from app.integrations.netbox.service import NetBoxService
from app.integrations.opensearch.service import OpenSearchActivityService
from app.ip_intelligence.schemas import IpSummary, ScanContext


def validate_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


class IpIntelligenceService:
    def __init__(self, netbox: NetBoxService, activity: OpenSearchActivityService) -> None:
        self.netbox = netbox
        self.activity = activity

    async def get_summary(
        self,
        ip: str,
        src_ip: str | None = None,
        dst_ip: str | None = None,
        dst_port: int | None = None,
    ) -> IpSummary:
        netbox_context = await self.netbox.lookup_ip(ip)
        activity_summary = await self.activity.summarize_ip(
            ip,
            src_ip=src_ip,
            dst_ip=dst_ip,
            dst_port=dst_port,
        )
        return IpSummary(
            ip=ip,
            netbox=netbox_context,
            scan=ScanContext(),
            activity=activity_summary,
        )
