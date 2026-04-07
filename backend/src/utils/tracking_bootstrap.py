"""Bootstrap helpers for tracking runtime services."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.config import Settings
from src.core.logger.logger import get_logger
from src.observability.metrics import MetricsRecorder
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.tracking.detectors.detector_pool import DetectorPool
from src.services.tracking.detectors.inference_detector import InferencePersonDetector
from src.services.tracking.identity.milvus_store import MilvusIdentityStore
from src.services.tracking.manager import TrackingStreamManager
from src.services.tracking.reid.embedder import TrackingReIdEmbedder
from src.services.tracking.reid.shared_embedding_service import SharedEmbeddingService
from src.services.tracking.updates import (
    FanoutTrackingUpdatePublisher,
    InferenceIngressPublisher,
    WebSocketTrackingUpdatePublisher,
)
from src.services.tracking_kafka.service import TrackingKafkaProducerService


@dataclass(slots=True)
class TrackingRuntimeServices:
    """Resolved tracking services shared with the FastAPI lifespan."""

    tracking_manager: TrackingStreamManager
    tracking_kafka_producer: TrackingKafkaProducerService


LOGGER = get_logger(__name__)


async def create_tracking_runtime_services(
    settings: Settings,
    websocket_manager: WebSocketManager,
    metrics_recorder: MetricsRecorder,
    inference_manager: object | None = None,
    tracking_kafka_producer: TrackingKafkaProducerService | None = None,
) -> TrackingRuntimeServices:
    """Build tracking services without blocking API startup on Milvus warmup."""

    if tracking_kafka_producer is None:
        tracking_kafka_producer = TrackingKafkaProducerService(settings)
        await tracking_kafka_producer.start()

    identity_store = MilvusIdentityStore(
        uri=settings.tracking_identity_store_uri,
        collection_name=settings.tracking_identity_collection_name,
        embedding_dimension=settings.tracking_identity_dimension,
        timeout_seconds=settings.tracking_identity_store_timeout_seconds,
        similarity_threshold=settings.tracking_identity_similarity_threshold,
        search_limit=settings.tracking_identity_search_limit,
        token=(
            settings.tracking_identity_store_token.get_secret_value()
            if settings.tracking_identity_store_token is not None
            else None
        ),
        metrics_recorder=metrics_recorder,
    )
    try:
        identity_store.ensure_ready()
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.warning(
            "Tracking identity store is unavailable during startup; "
            "the backend will continue without blocking API startup: %s",
            exc,
        )

    # Build a detector pool sized to the number of active cameras.  We
    # create one InferencePersonDetector per pool slot so each worker gets
    # exclusive, thread-safe access to its own model instance (BN-1).
    _api_key = (
        settings.tracking_detector_api_key.get_secret_value()
        if settings.tracking_detector_api_key is not None
        else None
    )
    detector_pool = DetectorPool(
        [
            InferencePersonDetector(
                settings.tracking_detector_model_id,
                confidence_threshold=settings.tracking_detector_confidence_threshold,
                iou_threshold=settings.tracking_detector_iou_threshold,
                target_class_name=settings.tracking_detector_target_class_name,
                api_key=_api_key,
            )
        ]
    )

    # Build the shared embedding service (one model, all workers, BN-4).
    embedder = TrackingReIdEmbedder(
        settings.tracking_embedder_name,
        weights_path=settings.tracking_embedder_weights_path,
    )
    shared_embedding_service = SharedEmbeddingService(embedder)

    tracking_manager = TrackingStreamManager(
        detector_pool=detector_pool,
        identity_store=identity_store,
        shared_embedding_service=shared_embedding_service,
        ffmpeg_binary=settings.ffmpeg_binary,
        rtsp_base_url=settings.mediamtx_rtsp_base_url,
        hls_base_url=settings.mediamtx_hls_base_url,
        whep_base_url=settings.mediamtx_webrtc_base_url,
        sample_fps=settings.tracking_sample_fps,
        output_fps=settings.tracking_output_fps,
        max_reconnect_attempts=settings.realtime_max_reconnect_attempts,
        tracking_suffix=settings.tracking_stream_suffix,
        tracker_lost_track_buffer=settings.tracking_tracker_lost_track_buffer,
        tracker_activation_threshold=settings.tracking_tracker_activation_threshold,
        tracker_minimum_consecutive_frames=(
            settings.tracking_tracker_minimum_consecutive_frames
        ),
        tracker_minimum_iou_threshold=settings.tracking_tracker_minimum_iou_threshold,
        tracker_high_conf_det_threshold=settings.tracking_tracker_high_conf_det_threshold,
        identity_sync_interval_seconds=settings.tracking_identity_sync_interval_seconds,
        publish_update_interval_seconds=settings.tracking_publish_update_interval_seconds,
        update_publisher=FanoutTrackingUpdatePublisher(
            [
                WebSocketTrackingUpdatePublisher(websocket_manager),
                tracking_kafka_producer.publisher(),
                *(
                    [InferenceIngressPublisher(inference_manager)]
                    if inference_manager is not None
                    else []
                ),
            ],
        ),
    )
    return TrackingRuntimeServices(
        tracking_manager=tracking_manager,
        tracking_kafka_producer=tracking_kafka_producer,
    )
