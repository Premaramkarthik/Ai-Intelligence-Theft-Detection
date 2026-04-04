"""HTTP middleware that records RED-style Prometheus metrics."""

# pylint: disable=too-few-public-methods

from __future__ import annotations

from time import perf_counter

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import BaseRoute

from src.observability.metrics import MetricsRecorder, NullMetricsRecorder


class HttpMetricsMiddleware(BaseHTTPMiddleware):
    """Record request count and latency for backend HTTP routes."""

    async def dispatch(self, request: Request, call_next) -> Response:
        metrics = _resolve_metrics_recorder(request)
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_seconds = perf_counter() - started_at
            metrics.observe_http_request(
                route=_resolve_route_template(request),
                method=request.method,
                status_code=500,
                duration_seconds=duration_seconds,
            )
            raise

        duration_seconds = perf_counter() - started_at
        metrics.observe_http_request(
            route=_resolve_route_template(request),
            method=request.method,
            status_code=response.status_code,
            duration_seconds=duration_seconds,
        )
        return response


def _resolve_metrics_recorder(request: Request) -> MetricsRecorder:
    """Return the metrics recorder stored in application state when available."""

    metrics = getattr(request.app.state, "metrics_recorder", None)
    if isinstance(metrics, MetricsRecorder):
        return metrics
    return NullMetricsRecorder()


def _resolve_route_template(request: Request) -> str:
    """Prefer the FastAPI route template over the raw URL path for labeling."""

    route = request.scope.get("route")
    if isinstance(route, BaseRoute):
        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            return path
        path_format = getattr(route, "path_format", None)
        if isinstance(path_format, str) and path_format:
            return path_format
    return request.url.path
