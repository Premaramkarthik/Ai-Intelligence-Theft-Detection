"""Async Triton gRPC client with bounded in-flight concurrency."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any

import numpy as np

from src.core.logger.logger import get_logger
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.services.inference.logging import (
    log_inference_event,
    log_inference_exception,
    mark_exception_logged,
    summarize_named_arrays,
    was_exception_logged,
)


class TritonInferenceClient:
    """Wrap the Triton gRPC async client with a semaphore concurrency cap.

    Args:
        url: Triton gRPC endpoint, e.g. "localhost:8001".
        max_in_flight: maximum number of concurrent outstanding requests.
    """

    def __init__(
        self,
        url: str,
        max_in_flight: int = 8,
        reconnect_interval_seconds: float = 5.0,
        metrics_recorder: PrometheusMetrics | NullMetricsRecorder | None = None,
    ) -> None:
        self._url = url
        self._max_in_flight = max_in_flight
        self._reconnect_interval_seconds = max(0.5, reconnect_interval_seconds)
        self._semaphore = asyncio.Semaphore(max_in_flight)
        self._client: Any = None  # tritonclientutils.InferenceServerClient at runtime
        self._connect_lock = asyncio.Lock()
        self._last_connect_attempt_at: float | None = None
        self._last_connect_error: str | None = None
        self._logger = get_logger(__name__)
        self._metrics_recorder = metrics_recorder or NullMetricsRecorder()

    async def connect(self) -> None:
        """Create the gRPC channel and verify server liveness."""

        async with self._connect_lock:
            await self._connect_locked()

    async def ensure_connected(self) -> bool:
        """Return ``True`` when Triton is currently connected or reconnect succeeds."""

        if self._client is not None:
            return True

        async with self._connect_lock:
            if self._client is not None:
                return True
            now = perf_counter()
            if (
                self._last_connect_attempt_at is not None
                and now - self._last_connect_attempt_at < self._reconnect_interval_seconds
            ):
                return False
            try:
                await self._connect_locked()
            except Exception:
                return False
            return self._client is not None

    async def _connect_locked(self) -> None:
        """Create the gRPC channel and verify server liveness under the connect lock."""

        import tritonclient.grpc.aio as triton_grpc  # pylint: disable=import-outside-toplevel

        connect_started_at = perf_counter()
        self._last_connect_attempt_at = connect_started_at
        log_inference_event(
            self._logger,
            logging.INFO,
            "inference.triton_connecting",
            "Connecting to Triton inference server.",
            triton_url=self._url,
            max_in_flight=self._max_in_flight,
        )
        try:
            client = triton_grpc.InferenceServerClient(url=self._url)
            if not await client.is_server_live():
                raise RuntimeError(f"Triton server at {self._url} is not live")
        except Exception as exc:  # pylint: disable=broad-except
            await self._safe_close_client_locally(locals().get("client"))
            self._client = None
            self._last_connect_error = str(exc)
            self._metrics_recorder.set_triton_connected(False)
            self._metrics_recorder.increment_triton_connect_failure()
            log_inference_exception(
                self._logger,
                logging.ERROR,
                "inference.triton_connect_error",
                "Triton connection attempt failed.",
                exc,
                triton_url=self._url,
                max_in_flight=self._max_in_flight,
                connect_latency_ms=round((perf_counter() - connect_started_at) * 1000.0, 3),
            )
            raise

        self._client = client
        self._last_connect_error = None
        self._metrics_recorder.set_triton_connected(True)
        log_inference_event(
            self._logger,
            logging.INFO,
            "inference.triton_connected",
            "Connected to Triton inference server.",
            triton_url=self._url,
            max_in_flight=self._max_in_flight,
            connect_latency_ms=round((perf_counter() - connect_started_at) * 1000.0, 3),
        )

    async def close(self) -> None:
        """Close the underlying gRPC channel."""

        if self._client is not None:
            await self._client.close()
            self._client = None
            self._metrics_recorder.set_triton_connected(False)
            log_inference_event(
                self._logger,
                logging.INFO,
                "inference.triton_closed",
                "Closed Triton inference client.",
                triton_url=self._url,
            )

    async def infer(
        self,
        model_name: str,
        inputs: dict[str, np.ndarray],
    ) -> dict[str, np.ndarray]:
        """Run one inference request against *model_name*.

        Args:
            model_name: Triton model repository name.
            inputs: dict mapping input name to numpy array.

        Returns:
            dict mapping output name to numpy array from Triton response.
        """

        import tritonclient.grpc.aio as triton_grpc  # pylint: disable=import-outside-toplevel

        if not await self.ensure_connected():
            exc = RuntimeError(
                f"Triton server at {self._url} is unavailable; "
                f"last_error={self._last_connect_error or 'connect_backoff_active'}"
            )
            mark_exception_logged(exc)
            raise exc

        request_started_at = perf_counter()
        log_inference_event(
            self._logger,
            logging.DEBUG,
            "inference.triton_request_started",
            "Submitting Triton gRPC inference request.",
            triton_url=self._url,
            model_name=model_name,
            inputs=summarize_named_arrays(inputs),
        )

        triton_inputs = []
        for name, array in inputs.items():
            inp = triton_grpc.InferInput(name, list(array.shape), "FP32")
            inp.set_data_from_numpy(array)
            triton_inputs.append(inp)

        try:
            async with self._semaphore:
                self._metrics_recorder.increment_triton_inflight_requests()
                try:
                    response = await self._client.infer(model_name=model_name, inputs=triton_inputs)
                finally:
                    self._metrics_recorder.decrement_triton_inflight_requests()
        except Exception as exc:  # pylint: disable=broad-except
            if self._is_connection_error(exc):
                await self._reset_client()
            if was_exception_logged(exc):
                log_inference_event(
                    self._logger,
                    logging.ERROR,
                    "inference.triton_request_failed",
                    "Triton inference request failed.",
                    triton_url=self._url,
                    model_name=model_name,
                    inputs=summarize_named_arrays(inputs),
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                    request_latency_ms=round((perf_counter() - request_started_at) * 1000.0, 3),
                )
            else:
                log_inference_exception(
                    self._logger,
                    logging.ERROR,
                    "inference.triton_request_failed",
                    "Triton inference request failed.",
                    exc,
                    triton_url=self._url,
                    model_name=model_name,
                    inputs=summarize_named_arrays(inputs),
                    request_latency_ms=round((perf_counter() - request_started_at) * 1000.0, 3),
                )
            raise

        outputs = {
            name: response.as_numpy(name)
            for name in response.get_output_names()
        }
        log_inference_event(
            self._logger,
            logging.DEBUG,
            "inference.triton_response_received",
            "Received Triton gRPC inference response.",
            triton_url=self._url,
            model_name=model_name,
            outputs=summarize_named_arrays(outputs),
            request_latency_ms=round((perf_counter() - request_started_at) * 1000.0, 3),
        )
        return outputs

    async def _reset_client(self) -> None:
        """Drop the active client so the next request attempts a reconnect."""

        client = self._client
        self._client = None
        self._metrics_recorder.set_triton_connected(False)
        await self._safe_close_client_locally(client)

    async def _safe_close_client_locally(self, client: Any) -> None:
        """Close a transient client instance without raising cleanup errors."""

        if client is None:
            return
        try:
            await client.close()
        except Exception:  # pylint: disable=broad-except
            pass

    @staticmethod
    def _is_connection_error(exc: BaseException) -> bool:
        message = str(exc).lower()
        return any(
            token in message
            for token in ("unavailable", "connection refused", "failed to connect", "connectex")
        )
