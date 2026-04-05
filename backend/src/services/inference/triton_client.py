"""Async Triton gRPC client with bounded in-flight concurrency."""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np

from src.core.logger.logger import get_logger


class TritonInferenceClient:
    """Wrap the Triton gRPC async client with a semaphore concurrency cap.

    Args:
        url: Triton gRPC endpoint, e.g. "localhost:8001".
        max_in_flight: maximum number of concurrent outstanding requests.
    """

    def __init__(self, url: str, max_in_flight: int = 8) -> None:
        self._url = url
        self._semaphore = asyncio.Semaphore(max_in_flight)
        self._client: Any = None  # tritonclientutils.InferenceServerClient at runtime
        self._logger = get_logger(__name__)

    async def connect(self) -> None:
        """Create the gRPC channel and verify server liveness."""
        import tritonclient.grpc.aio as triton_grpc  # pylint: disable=import-outside-toplevel

        self._client = triton_grpc.InferenceServerClient(url=self._url)
        if not await self._client.is_server_live():
            raise RuntimeError(f"Triton server at {self._url} is not live")

    async def close(self) -> None:
        """Close the underlying gRPC channel."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def infer(
        self,
        model_name: str,
        inputs: dict[str, np.ndarray],
    ) -> dict[str, np.ndarray]:
        """Run one inference request against *model_name*.

        Args:
            model_name: Triton model repository name.
            inputs: dict mapping input name → numpy array.

        Returns:
            dict mapping output name → numpy array from Triton response.
        """
        import tritonclient.grpc.aio as triton_grpc  # pylint: disable=import-outside-toplevel

        triton_inputs = []
        for name, array in inputs.items():
            inp = triton_grpc.InferInput(name, list(array.shape), "FP32")
            inp.set_data_from_numpy(array)
            triton_inputs.append(inp)

        async with self._semaphore:
            response = await self._client.infer(model_name=model_name, inputs=triton_inputs)

        return {
            output.name(): response.as_numpy(output.name())
            for output in response.get_output_names()
        }
