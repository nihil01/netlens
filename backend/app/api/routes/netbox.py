from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.dependencies import get_current_user
from app.integrations.netbox.service import NetBoxDeviceNotFound, NetBoxService
from app.ip_intelligence.schemas import NetBoxDeviceDetail, NetBoxInventory, NetBoxRegionsResponse

router = APIRouter()
netbox_service = NetBoxService()


@router.get("/netbox/regions", response_model=NetBoxRegionsResponse)
async def get_regions(_: Annotated[dict, Depends(get_current_user)]) -> NetBoxRegionsResponse:
    return await netbox_service.fetch_all()


@router.get("/netbox/inventory", response_model=NetBoxInventory)
async def get_netbox_inventory(_: Annotated[dict, Depends(get_current_user)]) -> NetBoxInventory:
    return await netbox_service.get_inventory()


@router.get("/netbox/devices/{device_id}/detail", response_model=NetBoxDeviceDetail)
async def get_netbox_device_detail(
    device_id: int, _: Annotated[dict, Depends(get_current_user)]
) -> NetBoxDeviceDetail:
    try:
        return await netbox_service.get_device_detail(device_id)
    except NetBoxDeviceNotFound as exc:
        raise HTTPException(status_code=404, detail="NetBox device not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"NetBox mapping error: {exc}") from exc


@router.post("/netbox/reset")
async def reset_netbox_data(
    _: Annotated[dict, Depends(get_current_user)], request: Request
) -> dict:
    scheduler = getattr(request.app.state, "scanner_scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scanner scheduler not initialized")
    result = await scheduler.reset_inventory_and_refresh()
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=502,
            detail=result.get("message") or "NetBox refresh failed after reset",
        )
    return result
