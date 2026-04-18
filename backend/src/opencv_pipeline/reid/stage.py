"""Body re-identification batch stage for tracked person crops."""

from __future__ import annotations

from time import perf_counter

from src.opencv_pipeline.contracts import ProcessedFrame, TrackedObject
from src.services.tracking.reid.embedder import TrackingReIdEmbedder
from src.utils.async_blocking import run_blocking_in_daemon_thread
from src.utils.image import crop_ltwh


class BodyReIdentifier:
    """Extract batched appearance embeddings for tracked person crops."""

    def __init__(self, embedder: TrackingReIdEmbedder) -> None:
        self._embedder = embedder

    async def enrich_tracks(
        self,
        assignments: list[tuple[ProcessedFrame, list[TrackedObject]]],
    ) -> float:
        """Mutate tracks in place with embeddings and return stage latency in ms."""

        crop_index: list[TrackedObject] = []
        crops = []
        started_at = perf_counter()
        for processed_frame, tracks in assignments:
            for track in tracks:
                crop = crop_ltwh(
                    processed_frame.working_bgr,
                    track.left,
                    track.top,
                    track.width,
                    track.height,
                )
                if crop is None:
                    continue
                crop_index.append(track)
                crops.append(crop)

        if not crops:
            return 0.0

        embeddings = await run_blocking_in_daemon_thread(self._embedder.embed, crops)
        for track, embedding in zip(crop_index, embeddings):
            track.embedding = embedding
        return (perf_counter() - started_at) * 1000.0
