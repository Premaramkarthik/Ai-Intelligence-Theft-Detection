"""Prometheus metrics HTTP server lifecycle helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from prometheus_client import CollectorRegistry, start_http_server


class MetricsServer:
    """Expose Prometheus metrics on a dedicated HTTP listener."""

    def __init__(
        self,
        port: int,
        host: str,
        registry: CollectorRegistry,
    ) -> None:
        """Store the server settings needed to expose a `/metrics` endpoint."""

        self._port = port
        self._host = host
        self._registry = registry
        self._http_server = None

    def start(self) -> None:
        """Start the Prometheus HTTP server if it is not already running."""

        if self._http_server is not None:
            return
        server = start_http_server(
            port=self._port,
            addr=self._host,
            registry=self._registry,
        )
        if hasattr(server, "shutdown"):
            self._http_server = server
            return
        if isinstance(server, tuple) and server:
            self._http_server = server[0]

    def stop(self) -> None:
        """Shut down the Prometheus HTTP server when supported by the client library."""

        if self._http_server is None:
            return
        shutdown = cast(
            Callable[[], Any] | None,
            getattr(self._http_server, "shutdown", None),
        )
        server_close = cast(
            Callable[[], Any] | None,
            getattr(self._http_server, "server_close", None),
        )
        if shutdown is not None:
            shutdown()
        if server_close is not None:
            server_close()
        self._http_server = None
