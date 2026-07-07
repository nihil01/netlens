from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.integrations.opensearch.export import build_excel_export
from app.integrations.opensearch.service import OpenSearchActivityService
from app.ip_intelligence.service import validate_ip_address

router = APIRouter()


def _get_opensearch_service() -> OpenSearchActivityService:
    return OpenSearchActivityService.from_settings()


@router.get("/ip/{ip}/domains")
async def get_ip_domain_activity(
    ip: str,
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[OpenSearchActivityService, Depends(_get_opensearch_service)],
    start: str | None = Query(default=None, description="Start timestamp (ISO)"),
    end: str | None = Query(default=None, description="End timestamp (ISO)"),
    size: int = Query(default=200, ge=1, le=2000, description="Max buckets"),
) -> dict[str, Any]:
    if not validate_ip_address(ip):
        raise HTTPException(status_code=422, detail="Invalid IP address")

    try:
        return await service.aggregate_domains_by_ip(
            ip=ip,
            start=start,
            end=end,
            size=size,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {exc}") from exc


@router.get("/ip/{ip}/export.xlsx")
async def export_ip_logs_excel(
    ip: str,
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[OpenSearchActivityService, Depends(_get_opensearch_service)],
    window: str = Query(default="24h", description="Time window (e.g. 24h, 7d, 30d)"),
    start: str | None = Query(default=None, description="Start timestamp (ISO)"),
    end: str | None = Query(default=None, description="End timestamp (ISO)"),
    size_per_source: int = Query(default=500, ge=1, le=5000, description="Max events per source"),
    src_ip: str | None = Query(default=None, description="Source IP filter"),
    dst_ip: str | None = Query(default=None, description="Destination IP filter"),
    dst_port: int | None = Query(default=None, ge=1, le=65535, description="Destination port filter"),
) -> StreamingResponse:
    if not validate_ip_address(ip):
        raise HTTPException(status_code=422, detail="Invalid IP address")
    if src_ip and not validate_ip_address(src_ip):
        raise HTTPException(status_code=422, detail="Invalid source IP address")
    if dst_ip and not validate_ip_address(dst_ip):
        raise HTTPException(status_code=422, detail="Invalid destination IP address")

    try:
        logs_data = await service.get_ip_logs(
            ip=ip,
            window=window,
            start=start,
            end=end,
            size_per_source=size_per_source,
            src_ip=src_ip,
            dst_ip=dst_ip,
            dst_port=dst_port,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {exc}") from exc

    summary_data = None
    try:
        summary = await service.summarize_ip(
            ip=ip,
            window=window,
            start=start,
            end=end,
            size_per_source=size_per_source,
            src_ip=src_ip,
            dst_ip=dst_ip,
            dst_port=dst_port,
        )
        summary_data = summary.model_dump()
    except Exception:
        pass

    domains_data = None
    try:
        domains_result = await service.aggregate_domains_by_ip(
            ip=ip,
            start=start,
            end=end,
            size=500,
        )
        domains_data = domains_result
    except Exception:
        pass

    buf = build_excel_export(
        ip=ip,
        logs_data=logs_data,
        summary_data=summary_data,
        domains_data=domains_data,
    )

    filename = f"netlens-{ip}-logs.xlsx"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
