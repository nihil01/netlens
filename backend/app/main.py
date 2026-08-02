from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.fmc_audit import router as fmc_audit_router
from app.api.routes.health import router as health_router
from app.api.routes.ip_intelligence import router as ip_intelligence_router
from app.api.routes.monitoring import router as monitoring_router
from app.api.routes.netbox import router as netbox_router
from app.api.routes.opensearch import router as opensearch_router
from app.api.routes.scanner import router as scanner_router
from app.api.routes.scheduler import router as scheduler_router
from app.core.config import get_settings
from app.db import close_db, init_db
from app.observability.logging import configure_logging
from app.scanner.scheduler import create_scanner_scheduler
from app.security.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Initialize DB tables
    settings = get_settings()
    if settings.database_url and settings.database_auto_create_schema:
        try:
            await init_db()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("DB init failed (audit module disabled): %s", exc)

    scheduler = create_scanner_scheduler()
    app.state.scanner_scheduler = scheduler
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()
        if settings.database_url:
            await close_db()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="NetLens API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(RateLimitMiddleware, settings=settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix="/api", tags=["auth"])
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(ip_intelligence_router, prefix="/api", tags=["ip-intelligence"])
    app.include_router(netbox_router, prefix="/api", tags=["netbox"])
    app.include_router(opensearch_router, prefix="/api", tags=["opensearch"])
    app.include_router(scanner_router, prefix="/api", tags=["scanner"])
    app.include_router(scheduler_router, prefix="/api", tags=["scheduler"])
    app.include_router(monitoring_router, prefix="/api", tags=["monitoring"])
    app.include_router(fmc_audit_router, prefix="/api", tags=["fmc-audit"])

    return app


app = create_app()
