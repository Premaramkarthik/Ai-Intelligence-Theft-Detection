"""Bootstrap helper for inference runtime services."""

from __future__ import annotations

from src.core.config import Settings
from src.core.db import Database
from src.observability.metrics import MetricsRecorder
from src.services.inference.event_repository import InferenceEventRepository
from src.services.inference.manager import InferenceManager
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.tracking_kafka.service import TrackingKafkaProducerService


def create_inference_runtime_services(
    settings: Settings,
    database: Database,
    websocket_manager: WebSocketManager,
    tracking_kafka_producer: TrackingKafkaProducerService,
    metrics_recorder: MetricsRecorder,
) -> InferenceManager:
    """Build and return an ``InferenceManager`` wired to shared infrastructure.

    The manager is returned immediately; individual camera orchestrators are
    started lazily via ``configure_stream(enabled=True)`` — either from the
    ``enable_inference`` flag on stream start or the PATCH endpoint.

    Args:
        settings: Application settings (provides Triton URL when added).
        database: Connected database — ``database.pool`` is passed to the
            event repository.
        websocket_manager: Shared WebSocket broadcaster for ``inference.updated``
            and ``inference.alert`` events.
        tracking_kafka_producer: The shared Kafka producer service; used to
            publish inference results to ``camera.ai_results``.
        metrics_recorder: Prometheus / null recorder for queue-depth metrics.
    """
    event_repository = InferenceEventRepository(database.pool)
    kafka_publisher = tracking_kafka_producer.inference_publisher(
        settings.kafka_topic_camera_ai_results
    )
    return InferenceManager(
        event_repository=event_repository,
        websocket_manager=websocket_manager,
        kafka_publisher=kafka_publisher,
        metrics_recorder=metrics_recorder,
        triton_url=settings.triton_url,
    )
