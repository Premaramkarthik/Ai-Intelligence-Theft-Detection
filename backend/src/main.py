"""Application entrypoint and lifecycle wiring for the backend."""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import Settings, get_settings
from src.core.db import Database
from src.core.exceptions.handler import register_exception_handlers
from src.core.logger.logger import configure_logging
from src.observability.http_middleware import HttpMetricsMiddleware
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.observability.metrics_server import MetricsServer
from src.observability.runtime_metrics import (
    RuntimeMetricsCollector,
    RuntimeMetricsDependencies,
)
from src.observability.system_metrics import SystemMetricsCollector
from src.routes.camera_routes import router as camera_router
from src.routes.health_routes import router as health_router
from src.routes.stream_routes import router as stream_router
from src.services.camera.camera_repository import CameraRepository
from src.services.camera.camera_service import CameraService
from src.services.camera.camera_validator import CameraValidator
from src.services.presentation.stream_contract_service import StreamContractService
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.realtime_video.alert_publisher import (
    WebSocketStreamConnectionAlertPublisher,
)
from src.services.realtime_video.mediamtx_service import MediaMtxService
from src.services.realtime_video.queue import FrameQueue
from src.services.realtime_video.stream_manager import MediaMtxStreamManager
from src.services.stream.kafka_event_consumer import StreamEventConsumer
from src.services.stream.stream_repository import StreamRepository
from src.services.stream.stream_service import StreamService
from src.services.tracking.manager import TrackingStreamManager
from src.services.tracking_kafka.service import TrackingKafkaProducerService
from src.utils.migration_runner import apply_pending_migrations
from src.utils.tracking_bootstrap import create_tracking_runtime_services


if sys.platform == "win32":
    # Windows selector loops do not implement asyncio subprocess transports.
    # This backend uses asyncio.create_subprocess_exec for ffprobe/MediaMTX flows,
    # so force the subprocess-capable policy before Uvicorn creates the server loop.
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@dataclass(slots=True)
class ApplicationContainer:  # pylint: disable=too-many-instance-attributes
    """Resolved application services shared across routes and background tasks."""

    settings: Settings
    database: Database
    camera_service: CameraService
    stream_service: StreamService
    mediamtx_service: MediaMtxService
    stream_manager: MediaMtxStreamManager
    tracking_manager: TrackingStreamManager
    tracking_kafka_producer: TrackingKafkaProducerService
    websocket_manager: WebSocketManager
    kafka_consumer: StreamEventConsumer
    metrics_server: MetricsServer | None
    system_metrics_collector: SystemMetricsCollector | None
    runtime_metrics_collector: RuntimeMetricsCollector | None
    started_at_epoch: float


def create_application() -> FastAPI:  # pylint: disable=too-many-statements
    """Create the FastAPI application and wire background runtime services."""

    settings = get_settings()
    configure_logging(settings.log_level, settings.json_logs)

    @asynccontextmanager
    async def lifespan(application: FastAPI):  # pylint: disable=too-many-locals,too-many-statements
        database = Database(settings)
        await database.connect()
        if settings.run_migrations_on_startup:
            async with database.pool.acquire() as connection:
                await apply_pending_migrations(connection)

        camera_repository = CameraRepository(database)
        stream_repository = StreamRepository(database)
        camera_validator = CameraValidator(settings)
        mediamtx_service = MediaMtxService(settings)
        frame_queue = FrameQueue(maxsize=settings.realtime_frame_queue_size)
        metrics_recorder = (
            PrometheusMetrics()
            if settings.metrics_enabled
            else NullMetricsRecorder()
        )
        metrics_server = None
        system_metrics_collector = None
        runtime_metrics_collector = None
        if settings.metrics_enabled:
            metrics_server = MetricsServer(
                port=settings.metrics_port,
                host=settings.metrics_host,
                registry=metrics_recorder.registry,
            )
            metrics_server.start()
            system_metrics_collector = SystemMetricsCollector(
                metrics=metrics_recorder,
                frame_queue=frame_queue,
                interval_seconds=settings.metrics_collection_interval_seconds,
            )
            await system_metrics_collector.start()
        application.state.metrics_recorder = metrics_recorder
        camera_service = CameraService(
            camera_repository,
            camera_validator,
            mediamtx_service,
        )
        cameras = await camera_service.list_all_camera_records()
        await mediamtx_service.sync_config(
            cameras,
            strict_runtime_sync=False,
        )
        websocket_manager = WebSocketManager(metrics_recorder=metrics_recorder)
        stream_contract_service = StreamContractService(settings)
        stream_manager = MediaMtxStreamManager(
            frame_queue,
            rtsp_base_url=settings.mediamtx_rtsp_base_url,
            hls_base_url=settings.mediamtx_hls_base_url,
            whep_base_url=settings.mediamtx_webrtc_base_url,
            max_reconnect_attempts=settings.realtime_max_reconnect_attempts,
            metrics_recorder=metrics_recorder,
        )
        stream_manager.set_connection_alert_publisher(
            WebSocketStreamConnectionAlertPublisher(
                camera_service,
                stream_repository,
                stream_manager,
                stream_contract_service,
                websocket_manager,
            ),
        )
        tracking_services = await create_tracking_runtime_services(
            settings,
            websocket_manager,
            metrics_recorder,
        )
        tracking_manager = tracking_services.tracking_manager
        tracking_kafka_producer = tracking_services.tracking_kafka_producer
        stream_service = StreamService(
            settings,
            camera_service,
            stream_repository,
            mediamtx_service,
            stream_manager,
            tracking_manager,
            stream_contract_service,
        )
        kafka_consumer = StreamEventConsumer(
            settings,
            stream_service,
            websocket_manager,
            metrics_recorder,
        )
        await kafka_consumer.start()
        if settings.metrics_enabled:
            runtime_metrics_collector = RuntimeMetricsCollector(
                metrics=metrics_recorder,
                dependencies=RuntimeMetricsDependencies(
                    stream_manager=stream_manager,
                    tracking_manager=tracking_manager,
                    tracking_kafka_producer=tracking_kafka_producer,
                    kafka_consumer=kafka_consumer,
                    mediamtx_service=mediamtx_service,
                ),
                interval_seconds=settings.metrics_collection_interval_seconds,
            )
            await runtime_metrics_collector.start()

        application.state.container = ApplicationContainer(
            settings=settings,
            database=database,
            camera_service=camera_service,
            stream_service=stream_service,
            mediamtx_service=mediamtx_service,
            stream_manager=stream_manager,
            tracking_manager=tracking_manager,
            tracking_kafka_producer=tracking_kafka_producer,
            websocket_manager=websocket_manager,
            kafka_consumer=kafka_consumer,
            metrics_server=metrics_server,
            system_metrics_collector=system_metrics_collector,
            runtime_metrics_collector=runtime_metrics_collector,
            started_at_epoch=time(),
        )
        try:
            yield
        finally:
            await kafka_consumer.stop()
            await tracking_kafka_producer.stop()
            await tracking_manager.close()
            await stream_manager.stop_all()
            if runtime_metrics_collector is not None:
                await runtime_metrics_collector.stop()
            if system_metrics_collector is not None:
                await system_metrics_collector.stop()
            if metrics_server is not None:
                metrics_server.stop()
            await mediamtx_service.stop()
            await database.disconnect()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Cameras", "description": "Camera CRUD and RTSP validation endpoints."},
            {"name": "Streams", "description": "Worker and playback contract endpoints."},
            {"name": "Health", "description": "Service, database, and stream health endpoints."},
        ],
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    application.add_middleware(HttpMetricsMiddleware)
    register_exception_handlers(application)
    application.include_router(camera_router)
    application.include_router(stream_router)
    application.include_router(health_router)
    return application


app = create_application()
