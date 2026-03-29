"""Protocols for realtime stream connection alerts."""

from __future__ import annotations

from typing import Protocol


class StreamConnectionAlertPublisher(Protocol):
    """Protocol implemented by publishers of worker connection alerts."""

    async def publish_camera_connected(self, camera_id: str) -> None:
        """Emit a one-shot alert after a camera stream begins producing frames."""


class NullStreamConnectionAlertPublisher:
    """No-op alert publisher used when no alert sink is configured."""

    async def publish_camera_connected(self, camera_id: str) -> None:
        """Discard the connection alert request."""

        del camera_id
