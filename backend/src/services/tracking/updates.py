from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Protocol

from src.core.logger.logger import get_logger
from src.schemas.common import WebSocketEnvelope
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.realtime_video.contracts import TrackingTrackSnapshot


class TrackingUpdatePublisher(Protocol):
    """Protocol implemented by tracking metadata broadcasters."""

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
    ) -> None:
        """Publish the latest tracking state."""


class NullTrackingUpdatePublisher:
    """Discard tracking updates when no broadcaster is configured."""

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
    ) -> None:
        del camera_id, stream_name, annotated_stream_name, tracks


class FanoutTrackingUpdatePublisher:
    """Fan out one tracking update to multiple downstream publishers."""

    def __init__(self, publishers: Iterable[TrackingUpdatePublisher]) -> None:
        self._publishers = tuple(publishers)
        self._logger = get_logger(__name__)

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
    ) -> None:
        results = await asyncio.gather(
            *(
                publisher.publish(
                    camera_id=camera_id,
                    stream_name=stream_name,
                    annotated_stream_name=annotated_stream_name,
                    tracks=tracks,
                )
                for publisher in self._publishers
            ),
            return_exceptions=True,
        )
        for publisher, result in zip(self._publishers, results):
            if isinstance(result, Exception):
                self._logger.warning(
                    "Tracking update publisher %s failed for camera %s: %s",
                    publisher.__class__.__name__,
                    camera_id,
                    result,
                )


class WebSocketTrackingUpdatePublisher:
    """Broadcast tracking updates through the existing websocket fanout."""

    def __init__(self, websocket_manager: WebSocketManager) -> None:
        self._websocket_manager = websocket_manager

    async def publish(
        self,
        *,
        camera_id: str,
        stream_name: str,
        annotated_stream_name: str,
        tracks: list[TrackingTrackSnapshot],
    ) -> None:
        await self._websocket_manager.broadcast(
            WebSocketEnvelope(
                type="tracking.updated",
                topic="tracking.updated",
                message="Tracking update available.",
                camera_id=camera_id,
                data={
                    "stream_name": stream_name,
                    "annotated_stream_name": annotated_stream_name,
                    "active_tracks": len(tracks),
                    "tracks": [
                        {
                            "track_id": track.track_id,
                            "persistent_id": track.persistent_id,
                            "class_name": track.class_name,
                            "confidence": track.confidence,
                            "similarity": track.similarity,
                            "left": track.left,
                            "top": track.top,
                            "width": track.width,
                            "height": track.height,
                            "sampled_at": track.sampled_at.isoformat(),
                            "age_frames": track.age_frames,
                            "consecutive_hits": track.consecutive_hits,
                            "frames_since_update": track.frames_since_update,
                            "persistent_id_state": track.persistent_id_state,
                        }
                        for track in tracks
                    ],
                },
            ),
        )
