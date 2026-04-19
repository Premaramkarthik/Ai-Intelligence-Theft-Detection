# """OpenCV worker entrypoint with optional RTSP bootstrap and local cv2 preview.

# This script keeps the worker on the same backend modules used elsewhere:

# 1. Camera inventory still flows through ``CameraService`` / PostgreSQL.
# 2. The OpenCV worker still runs through ``OpenCvPipelineRuntime``.
# 3. Tracking, identity, inference, Kafka, and metrics wiring all stay intact.

# When this file is run directly, the local annotated cv2 preview is enabled by
# default so the RTSP stream can be inspected visually without extra config.
# """

# """
# I0419 20:55:51.467011 1 grpc_server.cc:366] "Thread started for CommonHandler"

# I0419 20:55:51.467391 1 infer_handler.cc:680] "New request handler for ModelInferHandler, 0"

# I0419 20:55:51.467570 1 infer_handler.h:1367] "Thread started for ModelInferHandler"

# I0419 20:55:51.467843 1 infer_handler.cc:680] "New request handler for ModelInferHandler, 0"

# I0419 20:55:51.467947 1 infer_handler.h:1367] "Thread started for ModelInferHandler"

# I0419 20:55:51.468228 1 stream_infer_handler.cc:128] "New request handler for ModelStreamInferHandler, 0"

# I0419 20:55:51.468308 1 infer_handler.h:1367] "Thread started for ModelStreamInferHandler"

# I0419 20:55:51.468319 1 grpc_server.cc:2463] "Started GRPCInferenceService at 0.0.0.0:8001"

# I0419 20:55:51.468566 1 http_server.cc:4694] "Started HTTPService at 0.0.0.0:8000"

# I0419 20:55:51.512408 1 http_server.cc:362] "Started Metrics Service at 0.0.0.0:8002"

# """


# # python main.py --rtsp-url "rtsp://admin:admin123@192.168.1.158:554/subStream1" --camera-name "Front Gate"

# from __future__ import annotations

# import argparse
# import asyncio
# import os
# import signal
# import sys
# from contextlib import suppress
# from dataclasses import dataclass, field
# from typing import Sequence

# from src.core.config import Settings, get_settings
# from src.core.db import Database
# from src.core.logger.logger import configure_logging, get_logger
# from src.models.camera import CameraStatus, RTSPTransport
# from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
# from src.observability.metrics_server import MetricsServer
# from src.observability.system_metrics import SystemMetricsCollector
# from src.opencv_pipeline.runtime import OpenCvPipelineRuntime
# from src.schemas.camera_requests import CreateCameraRequest, UpdateCameraRequest
# from src.services.camera.camera_repository import CameraRepository
# from src.services.camera.camera_service import CameraService
# from src.services.camera.camera_validator import CameraValidator
# from src.services.inference.bootstrap import create_inference_runtime_services
# from src.services.presentation.websocket_manager import WebSocketManager
# from src.services.tracking_kafka.service import TrackingKafkaProducerService
# from src.utils.migration_runner import apply_pending_migrations


# if sys.platform == "win32":
#     asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


# BOOTSTRAP_METADATA_SOURCE = "backend.main"
# DEFAULT_BOOTSTRAP_TAGS = ["bootstrap", "opencv_pipeline", "rtsp"]
# SUPPORTED_INFERENCE_STRATEGIES = ("vjepa_probe", "cnn_transformer")


# @dataclass(slots=True)
# class WorkerLaunchOptions:
#     """Resolved command-line / environment launch options for the worker."""

#     rtsp_url: str | None = None
#     camera_name: str = "OpenCV Preview Camera"
#     camera_location: str | None = None
#     transport: RTSPTransport = RTSPTransport.tcp
#     tags: list[str] = field(default_factory=lambda: list(DEFAULT_BOOTSTRAP_TAGS))
#     validate_rtsp_on_startup: bool = False
#     validate_timeout_seconds: int = 8
#     display_enabled: bool = True
#     display_window_prefix: str = "OpenCV Pipeline"
#     enable_behavior_inference: bool | None = None
#     inference_strategy: str | None = None


# def _env_flag(name: str, default: bool = False) -> bool:
#     raw_value = os.getenv(name)
#     if raw_value is None:
#         return default
#     normalized = raw_value.strip().lower()
#     if normalized in {"1", "true", "yes", "on"}:
#         return True
#     if normalized in {"0", "false", "no", "off"}:
#         return False
#     return default


# def _env_optional_flag(name: str) -> bool | None:
#     raw_value = os.getenv(name)
#     if raw_value is None:
#         return None
#     normalized = raw_value.strip().lower()
#     if normalized in {"1", "true", "yes", "on"}:
#         return True
#     if normalized in {"0", "false", "no", "off"}:
#         return False
#     return None


# def _parse_transport(value: str | None) -> RTSPTransport:
#     if not value:
#         return RTSPTransport.tcp
#     try:
#         return RTSPTransport(value.strip().lower())
#     except ValueError:
#         return RTSPTransport.tcp


# def _parse_tags(value: str | None) -> list[str]:
#     if not value:
#         return list(DEFAULT_BOOTSTRAP_TAGS)
#     parsed = [tag.strip() for tag in value.split(",") if tag.strip()]
#     return parsed or list(DEFAULT_BOOTSTRAP_TAGS)


# def _parse_args(argv: Sequence[str] | None = None) -> WorkerLaunchOptions:
#     """Return worker launch options from CLI flags with env-based defaults."""

#     display_default = _env_optional_flag("OPENCV_PIPELINE_DISPLAY_ENABLED")
#     inference_enabled_default = _env_optional_flag("OPENCV_PIPELINE_ENABLE_BEHAVIOR_INFERENCE")
#     parser = argparse.ArgumentParser(
#         description=(
#             "Run the backend OpenCV worker with optional RTSP bootstrap and "
#             "local cv2 preview of the annotated stream."
#         )
#     )
#     parser.add_argument(
#         "--rtsp-url",
#         default=os.getenv("OPENCV_PIPELINE_RTSP_URL") or os.getenv("RTSP_URL"),
#         help="Direct RTSP URL to bootstrap into the camera inventory before the worker starts.",
#     )
#     parser.add_argument(
#         "--camera-name",
#         default=os.getenv("OPENCV_PIPELINE_RTSP_CAMERA_NAME", "OpenCV Preview Camera"),
#         help="Display name for the bootstrapped RTSP camera.",
#     )
#     parser.add_argument(
#         "--camera-location",
#         default=os.getenv("OPENCV_PIPELINE_RTSP_LOCATION"),
#         help="Optional location label stored with the bootstrapped camera.",
#     )
#     parser.add_argument(
#         "--transport",
#         choices=[transport.value for transport in RTSPTransport],
#         default=os.getenv("OPENCV_PIPELINE_RTSP_TRANSPORT", RTSPTransport.tcp.value),
#         help="RTSP transport to persist for the bootstrapped camera.",
#     )
#     parser.add_argument(
#         "--tags",
#         default=os.getenv("OPENCV_PIPELINE_RTSP_TAGS"),
#         help="Comma-separated tags stored on the bootstrapped camera.",
#     )
#     parser.add_argument(
#         "--validate-rtsp",
#         action=argparse.BooleanOptionalAction,
#         default=_env_flag("OPENCV_PIPELINE_VALIDATE_RTSP_ON_STARTUP", default=False),
#         help="Validate the RTSP source before the worker begins processing.",
#     )
#     parser.add_argument(
#         "--validate-timeout-seconds",
#         type=int,
#         default=int(os.getenv("OPENCV_PIPELINE_VALIDATE_TIMEOUT_SECONDS", "8") or "8"),
#         help="Validation timeout used when --validate-rtsp is enabled.",
#     )
#     parser.add_argument(
#         "--display",
#         dest="display_enabled",
#         action=argparse.BooleanOptionalAction,
#         default=display_default,
#         help="Enable or disable the local annotated cv2 preview window.",
#     )
#     parser.add_argument(
#         "--display-window-prefix",
#         default=os.getenv("OPENCV_PIPELINE_DISPLAY_WINDOW_PREFIX", "OpenCV Pipeline"),
#         help="Window-title prefix for the local cv2 preview.",
#     )
#     parser.add_argument(
#         "--enable-inference",
#         dest="enable_behavior_inference",
#         action=argparse.BooleanOptionalAction,
#         default=inference_enabled_default,
#         help="Enable or disable behavior inference for this worker process.",
#     )
#     parser.add_argument(
#         "--inference-strategy",
#         choices=SUPPORTED_INFERENCE_STRATEGIES,
#         default=os.getenv("OPENCV_PIPELINE_INFERENCE_STRATEGY"),
#         help="Default inference strategy for cameras without an API override.",
#     )

#     args = parser.parse_args(list(argv) if argv is not None else None)
#     return WorkerLaunchOptions(
#         rtsp_url=args.rtsp_url,
#         camera_name=args.camera_name,
#         camera_location=args.camera_location,
#         transport=_parse_transport(args.transport),
#         tags=_parse_tags(args.tags),
#         validate_rtsp_on_startup=bool(args.validate_rtsp),
#         validate_timeout_seconds=max(1, int(args.validate_timeout_seconds)),
#         display_enabled=True if args.display_enabled is None else bool(args.display_enabled),
#         display_window_prefix=args.display_window_prefix,
#         enable_behavior_inference=args.enable_behavior_inference,
#         inference_strategy=args.inference_strategy,
#     )


# def _apply_launch_overrides(settings: Settings, options: WorkerLaunchOptions) -> None:
#     """Apply worker-only launch overrides on top of loaded settings."""

#     settings.opencv_pipeline_display_enabled = options.display_enabled
#     settings.opencv_pipeline_display_window_prefix = options.display_window_prefix
#     if options.enable_behavior_inference is not None:
#         settings.opencv_pipeline_enable_behavior_inference = options.enable_behavior_inference
#     if options.inference_strategy is not None:
#         settings.opencv_pipeline_inference_strategy = options.inference_strategy


# async def _bootstrap_rtsp_camera(
#     camera_service: CameraService,
#     options: WorkerLaunchOptions,
# ) -> None:
#     """Ensure a direct RTSP camera exists when a bootstrap RTSP URL is supplied."""

#     if not options.rtsp_url:
#         return

#     logger = get_logger(__name__)
#     metadata = {
#         "bootstrap_source": BOOTSTRAP_METADATA_SOURCE,
#         "bootstrap_mode": "direct_rtsp_url",
#     }

#     cameras = await camera_service.list_all_camera_records()
#     existing_camera = next(
#         (camera for camera in cameras if camera.direct_rtsp_url == options.rtsp_url),
#         None,
#     )
#     if existing_camera is None:
#         existing_camera = next(
#             (
#                 camera
#                 for camera in cameras
#                 if camera.metadata.get("bootstrap_source") == BOOTSTRAP_METADATA_SOURCE
#             ),
#             None,
#         )

#     target_camera_id: str | None = None
#     if existing_camera is None:
#         created = await camera_service.create_camera(
#             CreateCameraRequest(
#                 name=options.camera_name,
#                 location=options.camera_location,
#                 direct_rtsp_url=options.rtsp_url,
#                 transport=options.transport,
#                 status=CameraStatus.active,
#                 metadata=metadata,
#                 tags=options.tags,
#             )
#         )
#         target_camera_id = created.id
#         logger.info(
#             "Bootstrapped RTSP camera for OpenCV pipeline: camera_id=%s name=%s",
#             created.id,
#             created.name,
#         )
#     else:
#         bootstrap_managed = (
#             existing_camera.metadata.get("bootstrap_source") == BOOTSTRAP_METADATA_SOURCE
#         )
#         updates: dict[str, object] = {}
#         if existing_camera.status != CameraStatus.active:
#             updates["status"] = CameraStatus.active
#         if bootstrap_managed:
#             if existing_camera.direct_rtsp_url != options.rtsp_url:
#                 updates["direct_rtsp_url"] = options.rtsp_url
#             if existing_camera.name != options.camera_name:
#                 updates["name"] = options.camera_name
#             if existing_camera.location != options.camera_location:
#                 updates["location"] = options.camera_location
#             if existing_camera.transport != options.transport:
#                 updates["transport"] = options.transport
#             merged_metadata = {**existing_camera.metadata, **metadata}
#             if merged_metadata != existing_camera.metadata:
#                 updates["metadata"] = merged_metadata
#             merged_tags = sorted({*existing_camera.tags, *options.tags})
#             if merged_tags != existing_camera.tags:
#                 updates["tags"] = merged_tags

#         if updates:
#             updated = await camera_service.update_camera(
#                 existing_camera.id,
#                 UpdateCameraRequest(**updates),
#             )
#             target_camera_id = updated.id
#             logger.info(
#                 "Updated RTSP bootstrap camera for OpenCV pipeline: camera_id=%s name=%s",
#                 updated.id,
#                 updated.name,
#             )
#         else:
#             target_camera_id = existing_camera.id
#             logger.info(
#                 "Using existing RTSP camera for OpenCV pipeline: camera_id=%s name=%s",
#                 existing_camera.id,
#                 existing_camera.name,
#             )

#     if target_camera_id is None or not options.validate_rtsp_on_startup:
#         return

#     validation = await camera_service.validate_camera(
#         target_camera_id,
#         timeout_seconds=options.validate_timeout_seconds,
#     )
#     level = logger.info if validation.is_reachable else logger.warning
#     level(
#         "Bootstrap RTSP validation completed: camera_id=%s reachable=%s code=%s latency_ms=%s",
#         validation.camera_id,
#         validation.is_reachable,
#         validation.code,
#         validation.latency_ms,
#     )


# async def _run(options: WorkerLaunchOptions) -> None:
#     settings = get_settings()
#     _apply_launch_overrides(settings, options)
#     configure_logging(
#         settings.log_level,
#         settings.json_logs,
#         enable_file_logging=settings.file_logs_enabled,
#         log_directory=settings.log_directory,
#         log_file_prefix=settings.log_file_prefix,
#         log_file_max_bytes=settings.log_file_max_bytes,
#         log_file_backup_count=settings.log_file_backup_count,
#         enable_subsystem_file_logging=settings.subsystem_logs_enabled,
#     )
#     logger = get_logger(__name__)
#     logger.info(
#         "Starting OpenCV worker: display=%s window_prefix=%s inference_enabled=%s "
#         "default_strategy=%s bootstrap_rtsp=%s",
#         settings.opencv_pipeline_display_enabled,
#         settings.opencv_pipeline_display_window_prefix,
#         settings.opencv_pipeline_enable_behavior_inference,
#         settings.opencv_pipeline_inference_strategy,
#         bool(options.rtsp_url),
#     )

#     database = Database(settings)
#     await database.connect()
#     if settings.run_migrations_on_startup:
#         async with database.pool.acquire() as connection:
#             await apply_pending_migrations(connection)

#     metrics_recorder = (
#         PrometheusMetrics() if settings.metrics_enabled else NullMetricsRecorder()
#     )
#     metrics_server = None
#     system_metrics_collector = None

#     camera_service = CameraService(
#         CameraRepository(database),
#         CameraValidator(settings),
#     )
#     await _bootstrap_rtsp_camera(camera_service, options)
#     active_cameras = await camera_service.list_active_camera_records()
#     if not active_cameras:
#         logger.warning(
#             "No active cameras are available for the OpenCV worker. "
#             "Provide --rtsp-url or activate a camera through the API."
#         )

#     websocket_manager = WebSocketManager(metrics_recorder=metrics_recorder)
#     tracking_kafka_producer = TrackingKafkaProducerService(settings, metrics_recorder)
#     await tracking_kafka_producer.start()
#     inference_manager = create_inference_runtime_services(
#         settings,
#         database,
#         websocket_manager,
#         tracking_kafka_producer,
#         metrics_recorder,
#     )
#     pipeline = OpenCvPipelineRuntime(
#         settings,
#         camera_service,
#         tracking_kafka_producer,
#         inference_manager,
#         metrics_recorder,
#         websocket_manager=websocket_manager,
#     )

#     try:
#         if settings.metrics_enabled:
#             metrics_server = MetricsServer(
#                 host=settings.metrics_host,
#                 port=settings.metrics_port,
#                 registry=metrics_recorder.registry,
#             )
#             metrics_server.start()
#             system_metrics_collector = SystemMetricsCollector(
#                 metrics=metrics_recorder,
#                 frame_queue=pipeline.frame_buffer,
#                 interval_seconds=settings.metrics_collection_interval_seconds,
#             )
#             await system_metrics_collector.start()

#         logger.info(
#             "OpenCV worker ready. "
#             "Live display shows: bounding boxes, persistent ID, confidence, "
#             "and inference label/score/alert-level when Triton results arrive. "
#             "Press Ctrl+C to stop."
#         )
#         stop_event = asyncio.Event()
#         loop = asyncio.get_running_loop()
#         for sig in (signal.SIGINT, signal.SIGTERM):
#             with suppress(NotImplementedError):
#                 loop.add_signal_handler(sig, stop_event.set)

#         pipeline_task = asyncio.create_task(pipeline.run_forever())
#         await stop_event.wait()
#         await pipeline.stop()
#         pipeline_task.cancel()
#         with suppress(asyncio.CancelledError):
#             await pipeline_task
#     finally:
#         await pipeline.stop()
#         pipeline.close()
#         await inference_manager.close()
#         await tracking_kafka_producer.stop()
#         if system_metrics_collector is not None:
#             await system_metrics_collector.stop()
#         if metrics_server is not None:
#             metrics_server.stop()
#         await database.disconnect()


# def main(argv: Sequence[str] | None = None) -> None:
#     options = _parse_args(argv)
#     asyncio.run(_run(options))


# if __name__ == "__main__":
#     main()
