"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    alerts,
    assistant,
    audit,
    auth,
    indicators,
    organizations,
    quality,
    reporting,
    reports,
    sync,
    sync_monitor,
    users,
)
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.13.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals to clients.
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message_ar": "حدث خطأ داخلي."}},
        )

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "service": "yhq-api", "version": "0.13.0"}

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(organizations.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(indicators.router, prefix="/api/v1")
    app.include_router(reporting.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(quality.router, prefix="/api/v1")
    app.include_router(assistant.router, prefix="/api/v1")
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(sync.router, prefix="/api/v1")
    app.include_router(sync_monitor.router, prefix="/api/v1")
    return app


app = create_app()
