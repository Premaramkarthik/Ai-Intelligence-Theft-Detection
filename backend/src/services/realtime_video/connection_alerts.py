"""Protocols for realtime stream connection alerts."""

from __future__ import annotations

from typing import Protocol


class StreamConnectionAlertPublisher(Protocol):
    """Protocol implemented by publishers of worker connection alerts."""

    async def publish_camera_connected(self, camera_id: str) -> None:
        """Emit a one-shot alert after a camera stream begins producing frames."""

    async def publish_camera_disconnected(
        self,
        camera_id: str,
        *,
        reconnect_attempts: int,
        error_message: str,
    ) -> None:
        """Emit a terminal alert after a camera exhausts its reconnect budget."""


class NullStreamConnectionAlertPublisher:
    """No-op alert publisher used when no alert sink is configured."""

    async def publish_camera_connected(self, camera_id: str) -> None:
        """Discard the connection alert request."""

        del camera_id

    async def publish_camera_disconnected(
        self,
        camera_id: str,
        *,
        reconnect_attempts: int,
        error_message: str,
    ) -> None:
        """Discard the disconnect alert request."""

        del camera_id, reconnect_attempts, error_message
