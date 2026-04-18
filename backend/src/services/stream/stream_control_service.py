from __future__ import annotations

from typing import Any

from src.models.camera import StreamRecord
from src.services.stream.stream_state_repository import StreamStateRepository


class StreamControlService:
    """Persist stream-scoped control settings that the worker consumes."""

    def __init__(self, repository: StreamStateRepository) -> None:
        self._repository = repository

    async def configure_inference(
        self,
        camera_id: str,
        *,
        enabled: bool | None = None,
        strategy: str | None = None,
    ) -> StreamRecord:
        current = await self._repository.fetch_by_camera_id(camera_id)
        metadata: dict[str, Any] = dict(current.metadata) if current is not None else {}
        inference_metadata = metadata.get("inference")
        if not isinstance(inference_metadata, dict):
            inference_metadata = {}

        if enabled is not None:
            inference_metadata["enabled"] = enabled
        if strategy is not None:
            inference_metadata["strategy"] = strategy

        metadata["inference"] = inference_metadata
        return await self._repository.upsert_metadata(camera_id, metadata)
