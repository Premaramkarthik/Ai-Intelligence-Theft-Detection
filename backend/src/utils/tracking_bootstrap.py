from __future__ import annotations

from dataclasses import dataclass

from src.core.config import Settings
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.tracking.detectors.yolo26_detector import Yolo26PersonDetector
from src.services.tracking.identity.milvus_store import MilvusIdentityStore
from src.services.tracking.manager import TrackingStreamManager
from src.services.tracking.updates import (
    FanoutTrackingUpdatePublisher,
    WebSocketTrackingUpdatePublisher,
)
from src.services.tracking_kafka.service import TrackingKafkaProducerService


@dataclass(slots=True)
class TrackingRuntimeServices:
    tracking_manager: TrackingStreamManager
    tracking_kafka_producer: TrackingKafkaProducerService


async def create_tracking_runtime_services(
    settings: Settings,
    websocket_manager: WebSocketManager,
) -> TrackingRuntimeServices:
    tracking_kafka_producer = TrackingKafkaProducerService(settings)
    await tracking_kafka_producer.start()

    identity_store = MilvusIdentityStore(
        uri=settings.tracking_identity_store_uri,
        collection_name=settings.tracking_identity_collection_name,
        embedding_dimension=settings.tracking_identity_dimension,
        similarity_threshold=settings.tracking_identity_similarity_threshold,
        search_limit=settings.tracking_identity_search_limit,
        token=(
            settings.tracking_identity_store_token.get_secret_value()
            if settings.tracking_identity_store_token is not None
            else None
        ),
    )
    identity_store.ensure_ready()

    tracking_manager = TrackingStreamManager(
        detector=Yolo26PersonDetector(
            settings.tracking_detector_model_path,
            input_size=settings.tracking_detector_input_size,
            confidence_threshold=settings.tracking_detector_confidence_threshold,
            iou_threshold=settings.tracking_detector_iou_threshold,
        ),
        identity_store=identity_store,
        ffmpeg_binary=settings.ffmpeg_binary,
        rtsp_base_url=settings.mediamtx_rtsp_base_url,
        hls_base_url=settings.mediamtx_hls_base_url,
        whep_base_url=settings.mediamtx_webrtc_base_url,
        sample_fps=settings.tracking_sample_fps,
        output_fps=settings.tracking_output_fps,
        max_reconnect_attempts=settings.realtime_max_reconnect_attempts,
        tracking_suffix=settings.tracking_stream_suffix,
        embedder_name=settings.tracking_embedder_name,
        embedder_weights_path=settings.tracking_embedder_weights_path,
        identity_sync_interval_seconds=settings.tracking_identity_sync_interval_seconds,
        publish_update_interval_seconds=settings.tracking_publish_update_interval_seconds,
        update_publisher=FanoutTrackingUpdatePublisher(
            (
                WebSocketTrackingUpdatePublisher(websocket_manager),
                tracking_kafka_producer.publisher(),
            ),
        ),
    )
    return TrackingRuntimeServices(
        tracking_manager=tracking_manager,
        tracking_kafka_producer=tracking_kafka_producer,
    )
