from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.integrations.netbox.service import NetBoxService
from app.ip_intelligence.schemas import NetBoxDeviceDetail, NetBoxInventory

router = APIRouter()


def get_netbox_service() -> NetBoxService:
    return NetBoxService.from_settings()


@router.get("/netbox/inventory", response_model=NetBoxInventory)
async def get_netbox_inventory(
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[NetBoxService, Depends(get_netbox_service)],
) -> NetBoxInventory:
    return await service.get_inventory()


@router.get("/netbox/devices/{device_id}/detail", response_model=NetBoxDeviceDetail)
async def get_netbox_device_detail(
    device_id: int,
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[NetBoxService, Depends(get_netbox_service)],
) -> NetBoxDeviceDetail:
    try:
        return await service.get_device_detail(device_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="NetBox device not found") from exc
        raise HTTPException(status_code=502, detail=f"NetBox HTTP error: {exc}") from exc
