"""FMC Audit & Change Intelligence API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.auth.dependencies import get_current_user, require_any_role, require_role
from app.integrations.fmc_audit.service import FmcAuditService

router = APIRouter()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _get_service() -> FmcAuditService:
    return FmcAuditService.from_settings()


@router.get("/fmc-audit/dashboard")
async def dashboard(
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcAuditService, Depends(_get_service)],
) -> dict[str, Any]:
    d = await service.get_dashboard()
    return d.model_dump()


@router.get("/fmc-audit/records")
async def list_records(
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcAuditService, Depends(_get_service)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = None,
    user: str | None = None,
    object_type: str | None = None,
    min_risk: int | None = None,
    since: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    date_from = _as_utc(date_from)
    date_to = _as_utc(date_to)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    result = await service.list_records(
        page=page,
        page_size=page_size,
        action=action,
        user=user,
        object_type=object_type,
        min_risk=min_risk,
        since=since,
        date_from=date_from,
        date_to=date_to,
    )
    return result.model_dump()


@router.get("/fmc-audit/records/{fmc_id}")
async def get_record(
    fmc_id: str,
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcAuditService, Depends(_get_service)],
) -> dict[str, Any] | None:
    result = await service.get_record(fmc_id)
    if not result:
        return None
    return result.model_dump()


@router.get("/fmc-audit/timeline")
async def timeline(
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcAuditService, Depends(_get_service)],
) -> dict[str, Any]:
    d = await service.get_dashboard()
    return {"timeline": d.timeline}


@router.get("/fmc-audit/users")
async def user_stats(
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcAuditService, Depends(_get_service)],
    name: str | None = None,
) -> list[dict[str, Any]]:
    stats = await service.get_user_stats(name)
    return [s.model_dump() for s in stats]


@router.get("/fmc-audit/relationships")
async def relationships(
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcAuditService, Depends(_get_service)],
    since_days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    graph = await service.get_relationships(since_days)
    return graph.model_dump()


@router.get("/fmc-audit/deployments")
async def deployments(
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcAuditService, Depends(_get_service)],
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    deps = await service.list_deployments(limit)
    return [d.model_dump() for d in deps]


@router.get("/fmc-audit/risk")
async def high_risk(
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[FmcAuditService, Depends(_get_service)],
    min_risk: int = Query(40, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    result = await service.list_records(min_risk=min_risk, page_size=limit)
    return result.model_dump()


@router.get("/fmc-audit/export")
async def export_records(
    _: Annotated[dict, Depends(require_any_role("admin", "export"))],
    service: Annotated[FmcAuditService, Depends(_get_service)],
    format: str = Query("csv"),
    since: str | None = None,
    action: str | None = None,
    user: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Any:
    date_from = _as_utc(date_from)
    date_to = _as_utc(date_to)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before date_to")
    data = await service.export_records(
        format=format,
        since=since,
        action=action,
        user=user,
        date_from=date_from,
        date_to=date_to,
    )
    if format == "csv":
        return PlainTextResponse(
            content=data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=fmc-audit.csv"},
        )
    return data


@router.post("/fmc-audit/refresh")
async def refresh(
    _: Annotated[dict, Depends(require_role("admin"))],
    service: Annotated[FmcAuditService, Depends(_get_service)],
) -> dict[str, Any]:
    return await service.refresh()
