from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user

router = APIRouter()


class CronUpdate(BaseModel):
    cron: str = Field(..., description="Cron expression (e.g. '0 2 * * *')", examples=["0 2 * * *"])


class EnabledUpdate(BaseModel):
    enabled: bool


def _get_scheduler(request: Request) -> Any:
    scheduler = getattr(request.app.state, "scanner_scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scanner scheduler not initialized")
    return scheduler


@router.get("/scheduler/status")
async def scheduler_status(
    _: Annotated[dict, Depends(get_current_user)],
    request: Request,
) -> dict[str, Any]:
    scheduler = _get_scheduler(request)
    return scheduler.get_status()


@router.get("/scheduler/history")
async def scheduler_history(
    _: Annotated[dict, Depends(get_current_user)],
    request: Request,
    limit: int = 20,
) -> dict[str, Any]:
    scheduler = _get_scheduler(request)
    return {"history": scheduler.get_history(limit=limit)}


@router.post("/scheduler/trigger")
async def scheduler_trigger(
    _: Annotated[dict, Depends(get_current_user)],
    request: Request,
) -> dict[str, Any]:
    scheduler = _get_scheduler(request)
    return scheduler.trigger_now()


@router.put("/scheduler/cron")
async def scheduler_update_cron(
    body: CronUpdate,
    _: Annotated[dict, Depends(get_current_user)],
    request: Request,
) -> dict[str, Any]:
    scheduler = _get_scheduler(request)
    return scheduler.update_cron(body.cron)


@router.put("/scheduler/enabled")
async def scheduler_set_enabled(
    body: EnabledUpdate,
    _: Annotated[dict, Depends(get_current_user)],
    request: Request,
) -> dict[str, Any]:
    scheduler = _get_scheduler(request)
    return scheduler.set_enabled(body.enabled)
