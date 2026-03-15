"""
Signaling service - FastAPI application factory.
Entry point: uvicorn services.signaling.main:app
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from services.signaling.api.router import api_router
from services.signaling.webrtc.peer_manager import peer_manager
from shared.core.settings import get_settings
from shared.db.session import DatabaseSession
from shared.logging.logger import get_logger

log = get_logger(__name__)
cfg = get_settings()
limiter = Limiter(key_func=get_remote_address)


def _cors_origins() -> list[str]:
    return cfg.cors_origin_list


def _validate_security_settings() -> None:
    cfg.validate_auth_settings(require_admin_credentials=True)
    if cfg.expose_metrics_api and not cfg.metrics_token:
        raise RuntimeError("METRICS_TOKEN must be configured when EXPOSE_METRICS_API=true")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    _validate_security_settings()
    application.state.redis = aioredis.from_url(cfg.redis_url, decode_responses=True)
    await application.state.redis.ping()

    application.state.db = DatabaseSession()
    await application.state.db.connect()
    await application.state.db.get_pool().fetchval("SELECT 1")

    log.info("Signaling service started")
    yield

    from shared.shm.ring_buffer import ReaderCache

    ReaderCache.clear()
    await peer_manager.close_all()
    await application.state.db.disconnect()
    await application.state.redis.aclose()
    log.info("Signaling service stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title="Pipeline Signaling API",
        version="0.4.0",
        docs_url="/docs" if cfg.enable_api_docs else None,
        redoc_url="/redoc" if cfg.enable_api_docs else None,
        lifespan=lifespan,
    )
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    if cfg.expose_metrics_api:
        @application.get("/metrics", include_in_schema=False)
        async def metrics(request: Request) -> Response:
            token = request.headers.get("x-metrics-token", "").strip()
            if token != cfg.metrics_token:
                raise HTTPException(status_code=404, detail="Not found")
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    application.include_router(api_router)
    return application


app = create_app()
