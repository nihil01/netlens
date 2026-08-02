"""Liveness, readiness, dependency health, and Prometheus text metrics."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, Request, Response, status
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db import session_scope
from app.monitoring.models import SourceFreshnessState
from app.observability.metrics import value as metric_value

router = APIRouter()


@router.get("/health")
@router.get("/health/live")
async def live() -> dict[str, str]:
    """Process liveness only; never couples container restarts to FMC availability."""
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict[str, Any]:
    """Readiness for internal dependencies required to serve local-state dashboards."""
    checks = await _internal_checks(request)
    ready_state = all(item["status"] in {"UP", "DISABLED"} for item in checks.values())
    if not ready_state:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "READY" if ready_state else "NOT_READY",
        "time": datetime.now(UTC).isoformat(),
        "checks": checks,
    }


@router.get("/health/dependencies")
async def dependencies(request: Request) -> dict[str, Any]:
    """Report internal probes plus external-source reachability/freshness."""
    settings = get_settings()
    internal = await _internal_checks(request)
    freshness = await _freshness_checks()
    netbox, opensearch = await asyncio.gather(
        _probe_netbox(settings),
        _probe_opensearch(settings),
    )
    fmc_sources = {
        name: item for name, item in freshness.items() if name.casefold().startswith("fmc")
    }
    fmc = _aggregate_fmc_freshness(fmc_sources, configured=bool(settings.fmc_url))
    return {
        "time": datetime.now(UTC).isoformat(),
        "dependencies": {
            **internal,
            "fmc": fmc,
            "netbox": netbox,
            "opensearch": opensearch,
        },
        "source_freshness": freshness,
    }


@router.get("/metrics", response_class=Response)
async def metrics() -> Response:
    """Expose bounded DB-backed internal metrics in Prometheus text format."""
    values = await _metric_values()
    lines = [
        "# HELP netlens_info NetLens process information.",
        "# TYPE netlens_info gauge",
        'netlens_info{service="netlens"} 1',
    ]
    for name, help_text, metric_type, value in values:
        lines.extend(
            [
                f"# HELP {name} {help_text}",
                f"# TYPE {name} {metric_type}",
                f"{name} {value}",
            ]
        )
    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


async def _internal_checks(request: Request) -> dict[str, dict[str, Any]]:
    settings = get_settings()
    database, redis_check = await asyncio.gather(
        _probe_database(settings.database_url),
        _probe_redis(settings.redis_url),
    )
    scheduler = getattr(request.app.state, "scanner_scheduler", None)
    scheduler_enabled = bool(
        scheduler
        and any(
            (
                scheduler._enabled,
                scheduler._inventory_enabled,
                scheduler._fmc_full_enabled,
                scheduler._fmc_components_enabled,
                scheduler._fmc_vpn_enabled,
                scheduler._fmc_audit_enabled,
                scheduler._retention_enabled,
            )
        )
    )
    scheduler_status = "UP" if scheduler and scheduler.scheduler.running else "DOWN"
    if not scheduler_enabled:
        scheduler_status = "DISABLED"
    return {
        "database": database,
        "redis": redis_check,
        "scheduler": {"status": scheduler_status},
    }


async def _probe_database(database_url: str) -> dict[str, Any]:
    if not database_url:
        return {"status": "DISABLED"}
    try:
        async with asyncio.timeout(3):
            async with session_scope() as session:
                await session.execute(text("SELECT 1"))
        return {"status": "UP"}
    except Exception as exc:
        return {"status": "DOWN", "error": type(exc).__name__}


async def _probe_redis(redis_url: str) -> dict[str, Any]:
    if not redis_url:
        return {"status": "DISABLED"}
    client = redis.from_url(redis_url, socket_timeout=3, socket_connect_timeout=3)
    try:
        async with asyncio.timeout(3):
            await client.ping()
        return {"status": "UP"}
    except Exception as exc:
        return {"status": "DOWN", "error": type(exc).__name__}
    finally:
        await client.aclose()


async def _freshness_checks() -> dict[str, dict[str, Any]]:
    settings = get_settings()
    if not settings.database_url:
        return {}
    try:
        async with asyncio.timeout(3):
            async with session_scope() as session:
                rows = list((await session.execute(select(SourceFreshnessState))).scalars())
        return {
            row.source: {
                "status": row.state,
                "last_attempt": row.last_attempt,
                "last_success": row.last_success,
                "duration_seconds": row.collection_duration_seconds,
                "records_received": row.records_received,
                "partial_result": row.partial_result,
                "error": row.error,
            }
            for row in rows
        }
    except Exception as exc:
        return {"database": {"status": "ERROR", "error": type(exc).__name__}}


def _aggregate_fmc_freshness(
    sources: dict[str, dict[str, Any]], *, configured: bool
) -> dict[str, Any]:
    if not configured:
        return {"status": "DISABLED", "sources": {}}
    if not sources:
        return {"status": "NEVER_COLLECTED", "sources": {}}
    priority = {
        "ERROR": 5,
        "STALE": 4,
        "DEGRADED": 3,
        "NEVER_COLLECTED": 2,
        "FRESH": 1,
    }
    worst = max(
        (str(item.get("status") or "NEVER_COLLECTED") for item in sources.values()),
        key=lambda state: priority.get(state, 2),
    )
    return {"status": worst, "sources": sources}


async def _probe_netbox(settings: Any) -> dict[str, Any]:
    if not settings.netbox_url or not settings.netbox_token:
        return {"status": "DISABLED"}
    headers = {"Authorization": f"Token {settings.netbox_token}"}
    return await _probe_http(
        f"{str(settings.netbox_url).rstrip('/')}/api/status/",
        verify=settings.netbox_verify_ssl,
        headers=headers,
    )


async def _probe_opensearch(settings: Any) -> dict[str, Any]:
    if not settings.opensearch_url:
        return {"status": "DISABLED"}
    auth = None
    if settings.opensearch_username and settings.opensearch_password:
        auth = (settings.opensearch_username, settings.opensearch_password)
    return await _probe_http(
        f"{str(settings.opensearch_url).rstrip('/')}/_cluster/health",
        verify=settings.opensearch_verify_ssl,
        auth=auth,
    )


async def _probe_http(
    url: str,
    *,
    verify: bool,
    headers: dict[str, str] | None = None,
    auth: tuple[str, str] | None = None,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(verify=verify, timeout=3) as client:
            result = await client.get(url, headers=headers, auth=auth)
        return {"status": "UP" if result.is_success else "DOWN", "http_status": result.status_code}
    except Exception as exc:
        return {"status": "DOWN", "error": type(exc).__name__}


async def _metric_values() -> list[tuple[str, str, str, int | float]]:
    from app.api.routes.monitoring import sse_client_count

    settings = get_settings()
    response_count = metric_value("fmc_response_time_seconds_count")
    response_mean = (
        metric_value("fmc_response_time_seconds_sum") / response_count if response_count else 0
    )
    collector_duration_count = metric_value("collector_duration_seconds_count")
    collector_duration_mean = (
        metric_value("collector_duration_seconds_sum") / collector_duration_count
        if collector_duration_count
        else 0
    )
    defaults: list[tuple[str, str, str, int | float]] = [
        (
            "collector_success_total",
            "Successful collector runs.",
            "counter",
            metric_value("collector_success_total"),
        ),
        (
            "collector_duration_seconds",
            "Mean collector duration.",
            "gauge",
            collector_duration_mean,
        ),
        (
            "scheduler_lag_seconds",
            "Most recently observed scheduler lag.",
            "gauge",
            metric_value("scheduler_lag_seconds"),
        ),
        (
            "collector_failure_total",
            "Failed collector runs.",
            "counter",
            metric_value("collector_failure_total"),
        ),
        (
            "records_collected_total",
            "Records received by collectors.",
            "counter",
            metric_value("records_collected_total"),
        ),
        (
            "fmc_http_requests_total",
            "Recorded FMC HTTP responses.",
            "counter",
            metric_value("fmc_http_requests_total"),
        ),
        (
            "fmc_http_errors_total",
            "Recorded FMC HTTP errors.",
            "counter",
            metric_value("fmc_http_errors_total"),
        ),
        ("fmc_response_time_seconds", "Mean FMC response time.", "gauge", response_mean),
        (
            "device_metrics_missing_total",
            "Persisted missing device metrics.",
            "counter",
            metric_value("device_metrics_missing_total"),
        ),
        ("stale_sources_total", "Sources currently stale or failed.", "gauge", 0),
        (
            "database_write_errors_total",
            "Observed database write errors.",
            "counter",
            metric_value("database_write_errors_total"),
        ),
        ("sse_clients", "Connected dashboard SSE clients.", "gauge", sse_client_count()),
    ]
    if not settings.database_url:
        return defaults
    try:
        async with asyncio.timeout(3):
            async with session_scope() as session:
                stale = await session.scalar(
                    select(func.count(SourceFreshnessState.source)).where(
                        SourceFreshnessState.state.in_(["STALE", "ERROR"])
                    )
                )
        replacements = {
            "stale_sources_total": int(stale or 0),
        }
        return [
            (name, help_text, kind, replacements.get(name, value))
            for name, help_text, kind, value in defaults
        ]
    except Exception:
        return defaults
