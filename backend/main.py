"""Edge worker bootstrap for the modular OpenCV pipeline runtime."""

from __future__ import annotations

import asyncio
import signal
import sys
from contextlib import suppress

from src.core.config import get_settings
from src.core.db import Database
from src.core.logger.logger import configure_logging
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.observability.metrics_server import MetricsServer
from src.observability.system_metrics import SystemMetricsCollector
from src.opencv_pipeline.runtime import OpenCvPipelineRuntime
from src.services.camera.camera_repository import CameraRepository
from src.services.camera.camera_service import CameraService
from src.services.camera.camera_validator import CameraValidator
from src.services.inference.bootstrap import create_inference_runtime_services
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.tracking_kafka.service import TrackingKafkaProducerService
from src.utils.migration_runner import apply_pending_migrations


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


async def _run() -> None:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        settings.json_logs,
        enable_file_logging=settings.file_logs_enabled,
        log_directory=settings.log_directory,
        log_file_prefix=settings.log_file_prefix,
        log_file_max_bytes=settings.log_file_max_bytes,
        log_file_backup_count=settings.log_file_backup_count,
    )

    database = Database(settings)
    await database.connect()
    if settings.run_migrations_on_startup:
        async with database.pool.acquire() as connection:
            await apply_pending_migrations(connection)

    metrics_recorder = (
        PrometheusMetrics() if settings.metrics_enabled else NullMetricsRecorder()
    )
    metrics_server = None
    system_metrics_collector = None

    camera_service = CameraService(
        CameraRepository(database),
        CameraValidator(settings),
    )
    websocket_manager = WebSocketManager(metrics_recorder=metrics_recorder)
    tracking_kafka_producer = TrackingKafkaProducerService(settings, metrics_recorder)
    await tracking_kafka_producer.start()
    inference_manager = create_inference_runtime_services(
        settings,
        database,
        websocket_manager,
        tracking_kafka_producer,
        metrics_recorder,
    )
    pipeline = OpenCvPipelineRuntime(
        settings,
        camera_service,
        tracking_kafka_producer,
        inference_manager,
        metrics_recorder,
    )

    try:
        if settings.metrics_enabled:
            metrics_server = MetricsServer(
                host=settings.metrics_host,
                port=settings.metrics_port,
                registry=metrics_recorder.registry,
            )
            metrics_server.start()
            system_metrics_collector = SystemMetricsCollector(
                metrics=metrics_recorder,
                frame_queue=pipeline.frame_buffer,
                interval_seconds=settings.metrics_collection_interval_seconds,
            )
            await system_metrics_collector.start()

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop_event.set)

        pipeline_task = asyncio.create_task(pipeline.run_forever())
        await stop_event.wait()
        await pipeline.stop()
        pipeline_task.cancel()
        with suppress(asyncio.CancelledError):
            await pipeline_task
    finally:
        await pipeline.stop()
        await inference_manager.close()
        await tracking_kafka_producer.stop()
        if system_metrics_collector is not None:
            await system_metrics_collector.stop()
        if metrics_server is not None:
            metrics_server.stop()
        await database.disconnect()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
