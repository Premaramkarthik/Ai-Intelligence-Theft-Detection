"""HTTP request metrics middleware."""

from __future__ import annotations

from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.observability.metrics import NullMetricsRecorder


class HttpMetricsMiddleware(BaseHTTPMiddleware):
    """Record per-route request counts, latency, and exception totals."""

    async def dispatch(self, request: Request, call_next):
        metrics = getattr(request.app.state, "metrics_recorder", None) or NullMetricsRecorder()
        route = _resolve_route_template(request)
        method = request.method.upper()
        started_at = perf_counter()
        metrics.increment_http_inprogress(route, method)
        try:
            response = await call_next(request)
        except Exception as exc:
            metrics.record_http_exception(route, method, exc.__class__.__name__)
            metrics.observe_http_request(route, method, 500, perf_counter() - started_at)
            raise
        finally:
            metrics.decrement_http_inprogress(route, method)
        metrics.observe_http_request(route, method, response.status_code, perf_counter() - started_at)
        return response


def _resolve_route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path
