from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


@dataclass(slots=True)
class RuntimeState:
    service_name: str
    booted: bool = False
    ready: bool = False
    degraded: bool = False
    started_at: float = field(default_factory=time.time)
    dependencies: dict[str, dict[str, Any]] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def set_booted(self, value: bool = True) -> None:
        self.booted = value

    def set_ready(self, value: bool = True) -> None:
        self.ready = value
        if value:
            self.degraded = False

    def set_degraded(self, value: bool = True) -> None:
        self.degraded = value
        if value:
            self.ready = False

    def dependency(self, name: str, ok: bool, detail: str | None = None) -> None:
        self.dependencies[name] = {"ok": ok, "detail": detail}

    def update_detail(self, **kwargs: Any) -> None:
        self.details.update(kwargs)

    def health_payload(self) -> dict[str, Any]:
        return {
            "service": self.service_name,
            "status": "alive" if self.booted else "starting",
            "booted": self.booted,
            "uptime_s": round(time.time() - self.started_at, 3),
        }

    def readiness_payload(self) -> dict[str, Any]:
        status = "ready" if self.ready else "degraded" if self.degraded else "starting"
        return {
            "service": self.service_name,
            "status": status,
            "ready": self.ready,
            "degraded": self.degraded,
            "dependencies": self.dependencies,
            "details": self.details,
            "uptime_s": round(time.time() - self.started_at, 3),
        }


async def start_runtime_server(
    state: RuntimeState,
    *,
    host: str,
    port: int,
) -> tuple[web.AppRunner, web.TCPSite]:
    app = web.Application()

    async def health(_request: web.Request) -> web.Response:
        return web.json_response(state.health_payload())

    async def ready(_request: web.Request) -> web.Response:
        payload = state.readiness_payload()
        return web.json_response(payload, status=200 if state.ready else 503)

    async def metrics(_request: web.Request) -> web.Response:
        return web.Response(body=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})

    app.router.add_get("/health", health)
    app.router.add_get("/ready", ready)
    app.router.add_get("/readiness", ready)
    app.router.add_get("/metrics", metrics)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    return runner, site
