from fastapi import APIRouter

from app.integrations.netbox.service import NetBoxService
from app.ip_intelligence.schemas import NetBoxRegionsResponse

netbox_service = NetBoxService()


router = APIRouter()


@router.get("/netbox/regions", response_model=NetBoxRegionsResponse)
async def get_regions() -> NetBoxRegionsResponse:
    return await netbox_service.fetch_all()
