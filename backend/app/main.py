from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.ip_intelligence import router as ip_intelligence_router
from app.api.routes.netbox import router as netbox_router
from app.core.config import get_settings
from app.scanner.scheduler import create_scanner_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = create_scanner_scheduler()
    app.state.scanner_scheduler = scheduler
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="NetLens API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(ip_intelligence_router, prefix="/api", tags=["ip-intelligence"])
    app.include_router(netbox_router, prefix="/api", tags=["netbox"])

    return app


app = create_app()