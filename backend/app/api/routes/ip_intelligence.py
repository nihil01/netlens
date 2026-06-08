from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_current_user
from app.integrations.netbox.service import NetBoxService
from app.integrations.opensearch.service import OpenSearchActivityService
from app.ip_intelligence.schemas import IpSummary
from app.ip_intelligence.service import IpIntelligenceService, validate_ip_address

router = APIRouter()


def get_ip_service() -> IpIntelligenceService:
    return IpIntelligenceService(
        netbox=NetBoxService.from_settings(),
        activity=OpenSearchActivityService.from_settings(),
    )


@router.get("/ip/{ip}/summary", response_model=IpSummary)
async def get_ip_summary(
    ip: str,
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[IpIntelligenceService, Depends(get_ip_service)],
    src_ip: Annotated[str | None, Query(description="Source IP filter for OpenSearch")] = None,
    dst_ip: Annotated[str | None, Query(description="Destination IP filter for OpenSearch")] = None,
    dst_port: Annotated[int | None, Query(ge=1, le=65535, description="Destination port filter for OpenSearch")] = None,
) -> IpSummary:
    if not validate_ip_address(ip):
        raise HTTPException(status_code=422, detail="Invalid IP address")
    if src_ip and not validate_ip_address(src_ip):
        raise HTTPException(status_code=422, detail="Invalid source IP address")
    if dst_ip and not validate_ip_address(dst_ip):
        raise HTTPException(status_code=422, detail="Invalid destination IP address")
    return await service.get_summary(ip, src_ip=src_ip, dst_ip=dst_ip, dst_port=dst_port)
