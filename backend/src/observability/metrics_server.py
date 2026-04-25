"""Dedicated Prometheus metrics HTTP server."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, start_http_server


class MetricsServer:
    """Expose Prometheus metrics on a dedicated HTTP listener."""

    def __init__(self, *, host: str, port: int, registry: CollectorRegistry) -> None:
        self._host = host
        self._port = port
        self._registry = registry
        self._server = None
        self._thread = None

    def start(self) -> None:
        if self._server is not None:
            return
        self._server, self._thread = start_http_server(
            self._port,
            addr=self._host,
            registry=self._registry,
        )

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None
