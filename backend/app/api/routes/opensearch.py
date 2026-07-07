from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.integrations.opensearch.export import build_excel_export
from app.integrations.opensearch.pdf_report import build_pdf_report
from app.integrations.opensearch.service import OpenSearchActivityService
from app.ip_intelligence.service import validate_ip_address

router = APIRouter()

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "logo.png")
if not os.path.exists(_LOGO_PATH):
    _LOGO_PATH = None


def _get_opensearch_service() -> OpenSearchActivityService:
    return OpenSearchActivityService.from_settings()


@router.get("/ip/{ip}/full-aggregation")
async def get_full_aggregation(
    ip: str,
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[OpenSearchActivityService, Depends(_get_opensearch_service)],
    start: str = Query(..., description="Start timestamp (ISO)"),
    end: str = Query(..., description="End timestamp (ISO)"),
    src_ip: str | None = Query(default=None, description="Source IP filter"),
    dst_ip: str | None = Query(default=None, description="Destination IP filter"),
    dst_port: int | None = Query(default=None, ge=1, le=65535, description="Destination port filter"),
    size: int = Query(default=500, ge=1, le=2000),
) -> dict[str, Any]:
    if not validate_ip_address(ip):
        raise HTTPException(status_code=422, detail="Invalid IP address")
    if src_ip and not validate_ip_address(src_ip):
        raise HTTPException(status_code=422, detail="Invalid source IP address")
    if dst_ip and not validate_ip_address(dst_ip):
        raise HTTPException(status_code=422, detail="Invalid destination IP address")
    try:
        return await service.aggregate_full_by_ip(
            ip=ip, start=start, end=end, size=size,
            src_ip=src_ip, dst_ip=dst_ip, dst_port=dst_port,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {exc}") from exc


@router.get("/ip/{ip}/export.xlsx")
async def export_ip_logs_excel(
    ip: str,
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[OpenSearchActivityService, Depends(_get_opensearch_service)],
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    src_ip: str | None = Query(default=None),
    dst_ip: str | None = Query(default=None),
    dst_port: int | None = Query(default=None, ge=1, le=65535),
    size_per_source: int = Query(default=500, ge=1, le=5000),
) -> StreamingResponse:
    if not validate_ip_address(ip):
        raise HTTPException(status_code=422, detail="Invalid IP address")

    window = "7d"
    try:
        logs_data = await service.get_ip_logs(
            ip=ip, window=window, start=start, end=end,
            size_per_source=size_per_source, src_ip=src_ip, dst_ip=dst_ip, dst_port=dst_port,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {exc}") from exc

    summary_data = None
    try:
        summary = await service.summarize_ip(
            ip=ip, window=window, start=start, end=end,
            size_per_source=size_per_source, src_ip=src_ip, dst_ip=dst_ip, dst_port=dst_port,
        )
        summary_data = summary.model_dump()
    except Exception:
        pass

    full_data = None
    try:
        full_data = await service.aggregate_full_by_ip(ip=ip, start=start, end=end, size=500)
    except Exception:
        pass

    buf = build_excel_export(ip=ip, logs_data=logs_data, summary_data=summary_data, full_data=full_data)
    filename = f"netlens-{ip}-logs.xlsx"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ip/{ip}/report.pdf")
async def export_ip_pdf_report(
    ip: str,
    _: Annotated[dict, Depends(get_current_user)],
    service: Annotated[OpenSearchActivityService, Depends(_get_opensearch_service)],
    start: str = Query(..., description="Start timestamp (ISO)"),
    end: str = Query(..., description="End timestamp (ISO)"),
    size: int = Query(default=500, ge=1, le=2000),
) -> StreamingResponse:
    if not validate_ip_address(ip):
        raise HTTPException(status_code=422, detail="Invalid IP address")

    try:
        full_data = await service.aggregate_full_by_ip(ip=ip, start=start, end=end, size=size)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {exc}") from exc

    logo_path = _LOGO_PATH
    # Try to find logo in frontend/public
    frontend_logo = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "frontend", "public", "logo.png")
    if os.path.exists(frontend_logo):
        logo_path = frontend_logo

    buf = build_pdf_report(ip=ip, full_data=full_data, logo_path=logo_path)
    filename = f"netlens-{ip}-report.pdf"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
