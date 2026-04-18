"""Application entrypoint and lifecycle wiring for the backend."""

from __future__ import annotations

import asyncio
import contextlib
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import Settings, get_settings
from src.core.db import Database
from src.core.exceptions.handler import register_exception_handlers
from src.core.logger.logger import configure_logging, get_logger
from src.observability.http_middleware import HttpMetricsMiddleware
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.observability.metrics_server import MetricsServer
from src.observability.runtime_metrics import (
    RuntimeMetricsCollector,
    RuntimeMetricsDependencies,
)
from src.observability.system_metrics import SystemMetricsCollector
from src.models.camera import CameraStatus, RTSPTransport
from src.opencv_pipeline.runtime import OpenCvPipelineRuntime
from src.routes.camera_routes import router as camera_router
from src.routes.health_routes import router as health_router
from src.routes.stream_routes import router as stream_router
from src.schemas.camera_requests import CreateCameraRequest, UpdateCameraRequest
from src.services.camera.camera_repository import CameraRepository
from src.services.camera.camera_service import CameraService
from src.services.camera.camera_validator import CameraValidator
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.inference.bootstrap import create_inference_runtime_services
from src.services.inference.manager import InferenceManager
from src.services.stream.stream_control_service import StreamControlService
from src.services.stream.kafka_event_consumer import StreamEventConsumer
from src.services.stream.stream_state_repository import StreamStateRepository
from src.services.tracking_kafka.service import TrackingKafkaProducerService
from src.utils.migration_runner import apply_pending_migrations


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
    stream_control_service: StreamControlService
    tracking_kafka_producer: TrackingKafkaProducerService
    inference_manager: InferenceManager
    opencv_pipeline: OpenCvPipelineRuntime
    websocket_manager: WebSocketManager
    stream_event_consumer: StreamEventConsumer | None
    metrics_server: MetricsServer | None
    system_metrics_collector: SystemMetricsCollector | None
    runtime_metrics_collector: RuntimeMetricsCollector | None
    started_at_epoch: float


_BOOTSTRAP_METADATA_SOURCE = "src.main"
_BOOTSTRAP_TAGS = ["bootstrap", "opencv_pipeline", "rtsp"]


async def _bootstrap_rtsp_camera(camera_service: CameraService, settings: Settings) -> None:
    """Upsert the env-configured RTSP camera so the pipeline has a camera to process."""

    rtsp_url = settings.opencv_pipeline_rtsp_url
    if not rtsp_url:
        return

    logger = get_logger(__name__)
    camera_name = settings.opencv_pipeline_rtsp_camera_name or "OpenCV Pipeline Camera"
    metadata = {"bootstrap_source": _BOOTSTRAP_METADATA_SOURCE, "bootstrap_mode": "direct_rtsp_url"}

    cameras = await camera_service.list_all_camera_records()
    existing = next(
        (c for c in cameras if c.direct_rtsp_url == rtsp_url),
        None,
    ) or next(
        (c for c in cameras if c.metadata.get("bootstrap_source") == _BOOTSTRAP_METADATA_SOURCE),
        None,
    )

    if existing is None:
        created = await camera_service.create_camera(
            CreateCameraRequest(
                name=camera_name,
                direct_rtsp_url=rtsp_url,
                transport=RTSPTransport.tcp,
                status=CameraStatus.active,
                metadata=metadata,
                tags=list(_BOOTSTRAP_TAGS),
            )
        )
        logger.info("Bootstrapped RTSP camera: camera_id=%s name=%s", created.id, created.name)
        return

    updates: dict[str, object] = {}
    if existing.status != CameraStatus.active:
        updates["status"] = CameraStatus.active
    if existing.metadata.get("bootstrap_source") == _BOOTSTRAP_METADATA_SOURCE:
        if existing.direct_rtsp_url != rtsp_url:
            updates["direct_rtsp_url"] = rtsp_url
        if existing.name != camera_name:
            updates["name"] = camera_name
        merged = {**existing.metadata, **metadata}
        if merged != existing.metadata:
            updates["metadata"] = merged
    if updates:
        updated = await camera_service.update_camera(existing.id, UpdateCameraRequest(**updates))
        logger.info("Updated bootstrap RTSP camera: camera_id=%s", updated.id)
    else:
        logger.info("Using existing RTSP camera: camera_id=%s", existing.id)


def create_application() -> FastAPI:  # pylint: disable=too-many-statements
    """Create the FastAPI application and wire background runtime services."""

    settings = get_settings()
    configure_logging(
        settings.log_level,
        settings.json_logs,
        enable_file_logging=settings.file_logs_enabled,
        log_directory=settings.log_directory,
        log_file_prefix=settings.log_file_prefix,
        log_file_max_bytes=settings.log_file_max_bytes,
        log_file_backup_count=settings.log_file_backup_count,
        enable_subsystem_file_logging=settings.subsystem_logs_enabled,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):  # pylint: disable=too-many-locals,too-many-statements
        database = Database(settings)
        await database.connect()
        if settings.run_migrations_on_startup:
            async with database.pool.acquire() as connection:
                await apply_pending_migrations(connection)

        camera_repository = CameraRepository(database)
        stream_state_repository = StreamStateRepository(database)
        camera_validator = CameraValidator(settings)
        metrics_recorder = (
            PrometheusMetrics()
            if settings.metrics_enabled
            else NullMetricsRecorder()
        )
        metrics_server = None
        system_metrics_collector = None
        runtime_metrics_collector = None
        stream_event_consumer = None
        if settings.metrics_enabled:
            metrics_server = MetricsServer(
                port=settings.metrics_port,
                host=settings.metrics_host,
                registry=metrics_recorder.registry,
            )
            metrics_server.start()
        application.state.metrics_recorder = metrics_recorder
        camera_service = CameraService(
            camera_repository,
            camera_validator,
        )
        stream_control_service = StreamControlService(stream_state_repository)
        websocket_manager = WebSocketManager(metrics_recorder=metrics_recorder)

        # Build the shared Kafka producer first so both inference and tracking
        # bootstraps can reference the same started producer instance.
        tracking_kafka_producer = TrackingKafkaProducerService(settings, metrics_recorder)
        await tracking_kafka_producer.start()

        # Inference manager is created before tracking so InferenceIngressPublisher
        # can be wired into the tracking fanout publisher.
        inference_manager = create_inference_runtime_services(
            settings,
            database,
            websocket_manager,
            tracking_kafka_producer,
            metrics_recorder,
        )
        await _bootstrap_rtsp_camera(camera_service, settings)
        opencv_pipeline = OpenCvPipelineRuntime(
            settings,
            camera_service,
            tracking_kafka_producer,
            inference_manager,
            metrics_recorder,
            websocket_manager=websocket_manager,
        )
        pipeline_task = asyncio.create_task(opencv_pipeline.run_forever())

        if settings.metrics_enabled:
            system_metrics_collector = SystemMetricsCollector(
                metrics=metrics_recorder,
                frame_queue=opencv_pipeline.frame_buffer,
                interval_seconds=settings.metrics_collection_interval_seconds,
            )
            await system_metrics_collector.start()

        stream_event_consumer = StreamEventConsumer(
            settings,
            stream_service=None,
            websocket_manager=websocket_manager,
            metrics_recorder=metrics_recorder,
        )
        await stream_event_consumer.start()
        if settings.metrics_enabled:
            runtime_metrics_collector = RuntimeMetricsCollector(
                metrics=metrics_recorder,
                dependencies=RuntimeMetricsDependencies(
                    tracking_kafka_producer=tracking_kafka_producer,
                    kafka_consumer=stream_event_consumer,
                ),
                interval_seconds=settings.metrics_collection_interval_seconds,
            )
            await runtime_metrics_collector.start()

        application.state.container = ApplicationContainer(
            settings=settings,
            database=database,
            camera_service=camera_service,
            stream_control_service=stream_control_service,
            tracking_kafka_producer=tracking_kafka_producer,
            inference_manager=inference_manager,
            opencv_pipeline=opencv_pipeline,
            websocket_manager=websocket_manager,
            stream_event_consumer=stream_event_consumer,
            metrics_server=metrics_server,
            system_metrics_collector=system_metrics_collector,
            runtime_metrics_collector=runtime_metrics_collector,
            started_at_epoch=time(),
        )
        try:
            yield
        finally:
            await opencv_pipeline.stop()
            pipeline_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pipeline_task
            opencv_pipeline.close()
            await inference_manager.close()
            if stream_event_consumer is not None:
                await stream_event_consumer.stop()
            await tracking_kafka_producer.stop()
            if runtime_metrics_collector is not None:
                await runtime_metrics_collector.stop()
            if system_metrics_collector is not None:
                await system_metrics_collector.stop()
            if metrics_server is not None:
                metrics_server.stop()
            await database.disconnect()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Cameras", "description": "Camera CRUD and RTSP validation endpoints."},
            {"name": "Health", "description": "Service and database endpoints."},
            {"name": "Streams", "description": "Realtime websocket and inference controls."},
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
    application.include_router(health_router)
    application.include_router(stream_router)
    return application


app = create_application()
