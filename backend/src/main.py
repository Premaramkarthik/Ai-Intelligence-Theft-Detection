from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import Settings, get_settings
from src.core.db import Database
from src.core.exceptions.handler import register_exception_handlers
from src.core.logger.logger import configure_logging
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.observability.metrics_server import MetricsServer
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


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    database: Database
    camera_service: CameraService
    stream_service: StreamService
    mediamtx_service: MediaMtxService
    stream_manager: MediaMtxStreamManager
    websocket_manager: WebSocketManager
    kafka_consumer: StreamEventConsumer
    metrics_server: MetricsServer | None
    system_metrics_collector: SystemMetricsCollector | None
    started_at_epoch: float


def create_application() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.json_logs)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(settings)
        await database.connect()

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
        websocket_manager = WebSocketManager()
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
        stream_service = StreamService(
            settings,
            camera_service,
            stream_repository,
            mediamtx_service,
            stream_manager,
            stream_contract_service,
        )
        kafka_consumer = StreamEventConsumer(settings, stream_service, websocket_manager)
        await kafka_consumer.start()

        app.state.container = ApplicationContainer(
            settings=settings,
            database=database,
            camera_service=camera_service,
            stream_service=stream_service,
            mediamtx_service=mediamtx_service,
            stream_manager=stream_manager,
            websocket_manager=websocket_manager,
            kafka_consumer=kafka_consumer,
            metrics_server=metrics_server,
            system_metrics_collector=system_metrics_collector,
            started_at_epoch=time(),
        )
        try:
            yield
        finally:
            await kafka_consumer.stop()
            await stream_manager.stop_all()
            if system_metrics_collector is not None:
                await system_metrics_collector.stop()
            if metrics_server is not None:
                metrics_server.stop()
            await mediamtx_service.stop()
            await database.disconnect()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Cameras", "description": "Camera CRUD and RTSP validation endpoints."},
            {"name": "Streams", "description": "Worker and playback contract endpoints."},
            {"name": "Health", "description": "Service, database, and stream health endpoints."},
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(camera_router)
    app.include_router(stream_router)
    app.include_router(health_router)
    return app


app = create_application()
