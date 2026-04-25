"""End-to-end runtime for the modular OpenCV edge processing pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter_ns
from typing import TYPE_CHECKING

from src.core.config import Settings
from src.core.logger.logger import get_logger
from src.models.camera import CameraRecord
from src.observability.metrics import NullMetricsRecorder, PrometheusMetrics
from src.opencv_pipeline.buffering.frame_buffer import FrameBuffer
from src.opencv_pipeline.buffering.synchronizer import MultiCameraSynchronizer
from src.opencv_pipeline.calibration.service import CalibrationService
from src.opencv_pipeline.contracts import FrameSourceConfig, PipelineOutput, utc_now
from src.opencv_pipeline.detection.yolo import YOLOBatchDetector
from src.opencv_pipeline.identity.service import IdentityAssignmentService
from src.opencv_pipeline.ingestion.capture import VideoCaptureWorker
from src.opencv_pipeline.motion.analyzer import MotionAnalyzer
from src.opencv_pipeline.output.publisher import FrameAnnotator, InferenceOverlayCache, OutputDispatcher
from src.opencv_pipeline.preprocessing.processor import FramePreprocessor
from src.opencv_pipeline.reid.stage import BodyReIdentifier
from src.opencv_pipeline.stabilization.stabilizer import OpticalFlowStabilizer
from src.opencv_pipeline.tracking.stage import ByteTrackStage
from src.services.camera.camera_service import CameraService
from src.services.inference.manager import InferenceManager
from src.services.presentation.websocket_manager import WebSocketManager
from src.services.tracking.identity.milvus_store import MilvusIdentityStore
from src.services.tracking.reid.embedder import TrackingReIdEmbedder
from src.services.tracking.updates import (
    FanoutTrackingUpdatePublisher,
    InferenceIngressPublisher,
    WebSocketTrackingUpdatePublisher,
)
from src.services.tracking_kafka.service import TrackingKafkaProducerService
from src.utils.ffmpeg import build_rtsp_url_from_camera

if TYPE_CHECKING:
    from src.services.webrtc.registry import WebRTCRegistry


@dataclass(slots=True)
class _ActiveCamera:
    source: FrameSourceConfig
    worker: VideoCaptureWorker


class OpenCvPipelineRuntime:
    """Own the modular capture-to-output pipeline for all active cameras."""

    def __init__(
        self,
        settings: Settings,
        camera_service: CameraService,
        tracking_kafka_producer: TrackingKafkaProducerService,
        inference_manager: InferenceManager,
        metrics_recorder: PrometheusMetrics | NullMetricsRecorder | None = None,
        websocket_manager: WebSocketManager | None = None,
        webrtc_registry: WebRTCRegistry | None = None,
    ) -> None:
        self._settings = settings
        self._camera_service = camera_service
        self._inference_manager = inference_manager
        self._metrics = metrics_recorder or NullMetricsRecorder()
        self._logger = get_logger(__name__)
        self._frame_buffer = FrameBuffer(
            maxsize=settings.opencv_pipeline_frame_buffer_size,
            drop_policy=settings.opencv_pipeline_drop_policy,
            use_shared_memory=settings.opencv_pipeline_shared_memory_enabled,
            frame_shape=(
                settings.opencv_pipeline_target_height,
                settings.opencv_pipeline_target_width,
                3,
            ),
            shared_memory_slots=settings.opencv_pipeline_shared_memory_slots,
        )
        self._calibration_service = CalibrationService()
        self._preprocessor = FramePreprocessor(
            target_width=settings.opencv_pipeline_target_width,
            target_height=settings.opencv_pipeline_target_height,
            low_light_threshold=settings.opencv_pipeline_low_light_threshold,
        )
        self._stabilizer = OpticalFlowStabilizer(self._preprocessor)
        self._motion_analyzer = MotionAnalyzer()
        self._detector = YOLOBatchDetector(
            settings.opencv_pipeline_detection_model_path,
            confidence_threshold=settings.opencv_pipeline_detection_confidence,
            class_ids=settings.opencv_pipeline_detection_class_ids,
            max_batch_size=settings.opencv_pipeline_batch_size,
        )
        self._tracker = ByteTrackStage(
            frame_rate=settings.opencv_pipeline_target_fps,
            lost_track_buffer=settings.tracking_tracker_lost_track_buffer,
            track_activation_threshold=settings.tracking_tracker_activation_threshold,
            minimum_consecutive_frames=settings.tracking_tracker_minimum_consecutive_frames,
            minimum_iou_threshold=settings.tracking_tracker_minimum_iou_threshold,
            high_conf_det_threshold=settings.tracking_tracker_high_conf_det_threshold,
        )
        embedder = TrackingReIdEmbedder(
            settings.tracking_embedder_name,
            weights_path=settings.tracking_embedder_weights_path,
        )
        self._reidentifier = BodyReIdentifier(embedder)
        identity_store = MilvusIdentityStore(
            uri=settings.tracking_identity_store_uri,
            collection_name=settings.tracking_identity_collection_name,
            embedding_dimension=settings.tracking_identity_dimension,
            timeout_seconds=settings.tracking_identity_store_timeout_seconds,
            similarity_threshold=settings.tracking_identity_similarity_threshold,
            search_limit=settings.tracking_identity_search_limit,
            max_concurrent_batches=settings.tracking_identity_max_concurrent_batches,
            token=(
                settings.tracking_identity_store_token.get_secret_value()
                if settings.tracking_identity_store_token is not None
                else None
            ),
        )
        self._identity_service = IdentityAssignmentService(
            identity_store,
            identity_ttl_seconds=settings.opencv_pipeline_identity_ttl_seconds,
        )
        publishers = [tracking_kafka_producer.publisher()]
        if websocket_manager is not None:
            publishers.append(WebSocketTrackingUpdatePublisher(websocket_manager))
        if settings.opencv_pipeline_enable_behavior_inference:
            publishers.append(InferenceIngressPublisher(inference_manager))
        self._tracking_update_publisher = FanoutTrackingUpdatePublisher(publishers)
        self._inference_cache = InferenceOverlayCache()
        inference_manager.set_result_callback(self._inference_cache.record)
        self._annotator = FrameAnnotator(inference_cache=self._inference_cache)
        self._dispatcher = OutputDispatcher(
            self._tracking_update_publisher,
            frame_publisher=tracking_kafka_producer.json_publisher(
                settings.kafka_topic_camera_frames
            ),
            identity_event_publisher=tracking_kafka_producer.json_publisher(
                settings.kafka_topic_identity_events
            ),
            ws_frame_publisher=websocket_manager,
            webrtc_registry=webrtc_registry,
            annotated_stream_suffix=settings.tracking_stream_suffix,
            display_enabled=settings.opencv_pipeline_display_enabled,
            display_window_prefix=settings.opencv_pipeline_display_window_prefix,
        )
        self._active_cameras: dict[str, _ActiveCamera] = {}
        self._camera_inference_controls: dict[str, tuple[bool, str]] = {}
        self._last_frame_seen_at: dict[str, datetime] = {}
        self._last_active_tracks: dict[str, int] = {}
        self._last_queue_latency_ms: dict[str, float] = {}
        self._last_decode_time_ms: dict[str, float] = {}
        self._last_stream_fps: dict[str, float] = {}
        self._last_reconnect_attempts: dict[str, int] = {}
        self._synchronizer = MultiCameraSynchronizer([], settings.opencv_pipeline_sync_tolerance_ms)
        self._sync_camera_ids: tuple[str, ...] = ()
        self._running = False

    @property
    def frame_buffer(self) -> FrameBuffer:
        """Expose the shared frame buffer for metrics collectors."""

        return self._frame_buffer

    async def start(self) -> None:
        """Start the runtime and ensure downstream dependencies are ready."""

        if not self._settings.opencv_pipeline_enabled or self._running:
            return
        self._identity_service.ensure_ready()
        await self.refresh_cameras()
        self._metrics.set_active_cameras(len(self._active_cameras))
        self._running = True

    async def stop(self) -> None:
        """Stop all capture workers and close downstream clients."""

        if not self._running and not self._active_cameras:
            return
        self._running = False
        for camera_id in list(self._active_cameras):
            await self._remove_camera(camera_id)
        self._identity_service.close()
        self._synchronizer.close()
        self._sync_camera_ids = ()
        self._metrics.set_active_cameras(0)

    def close(self) -> None:
        """Release runtime-owned buffering resources."""

        self._dispatcher.close()
        self._synchronizer.close()
        self._sync_camera_ids = ()
        self._frame_buffer.close()

    async def run_forever(self) -> None:
        """Run the pipeline until ``stop()`` is called."""

        await self.start()
        refresh_started_at = utc_now()
        inference_control_refresh_started_at = utc_now()
        try:
            while self._running:
                if not self._active_cameras:
                    await asyncio.sleep(1.0)
                now = utc_now()
                if (
                    now - refresh_started_at
                ).total_seconds() >= self._settings.opencv_pipeline_refresh_all_cameras_interval_seconds:
                    await self.refresh_cameras()
                    refresh_started_at = now
                if (
                    now - inference_control_refresh_started_at
                ).total_seconds() >= (
                    self._settings.opencv_pipeline_inference_control_refresh_interval_seconds
                ):
                    await self.sync_inference_controls()
                    inference_control_refresh_started_at = now

                packet = await self._frame_buffer.get()
                if packet.camera_id not in self._active_cameras:
                    self._metrics.record_frame_dropped(packet.camera_id, reason="inactive_camera")
                    packet.release()
                    continue

                queue_latency_ms = (
                    perf_counter_ns() - packet.monotonic_ns
                ) / 1_000_000.0
                self._last_queue_latency_ms[packet.camera_id] = queue_latency_ms
                self._metrics.set_stream_queue_latency_ms(packet.camera_id, queue_latency_ms)
                self._last_frame_seen_at[packet.camera_id] = packet.captured_at
                self._refresh_sync_group(packet.captured_at, packet.camera_id)
                bundle = self._synchronizer.submit(packet)
                if bundle is None:
                    continue
                await self._process_bundle(bundle)
        finally:
            await self.stop()

    async def refresh_cameras(self) -> None:
        """Refresh active cameras from PostgreSQL and start/stop workers as needed."""

        camera_records = await self._camera_service.list_active_camera_records()
        target_sources = {
            camera.id: self._build_source_config(camera)
            for camera in camera_records
        }
        topology_changed = False

        for camera_id in list(self._active_cameras):
            if camera_id in target_sources:
                if self._active_cameras[camera_id].source == target_sources[camera_id]:
                    continue
            topology_changed = True
            await self._remove_camera(camera_id)

        for camera_id, source in target_sources.items():
            if camera_id in self._active_cameras:
                continue
            topology_changed = True
            worker = VideoCaptureWorker(
                source,
                self._frame_buffer,
                retry_initial_delay_seconds=(
                    self._settings.opencv_pipeline_capture_retry_initial_delay_seconds
                ),
                retry_max_delay_seconds=(
                    self._settings.opencv_pipeline_capture_retry_max_delay_seconds
                ),
                metrics_recorder=self._metrics,
            )
            worker.start()
            self._active_cameras[camera_id] = _ActiveCamera(source=source, worker=worker)
            self._load_calibration_profile(source)

        await self._sync_inference_controls(camera_records)
        if topology_changed:
            self._refresh_sync_group(utc_now(), None)
        self._metrics.set_active_cameras(len(self._active_cameras))
        self._metrics.set_stream_worker_count(len(self._active_cameras))
        self._metrics.set_tracking_worker_count(len(self._active_cameras))

    async def sync_inference_controls(self) -> None:
        """Refresh per-camera inference settings without rebuilding capture topology."""

        if not self._active_cameras:
            return
        camera_records = await self._camera_service.list_active_camera_records()
        await self._sync_inference_controls(camera_records)

    async def _remove_camera(self, camera_id: str) -> None:
        active_camera = self._active_cameras.pop(camera_id, None)
        if active_camera is None:
            return
        active_camera.worker.stop()
        discarded_frames = self._frame_buffer.discard_camera(camera_id)
        self._tracker.remove_camera(camera_id)
        self._stabilizer.remove_camera(camera_id)
        self._inference_cache.remove_camera(camera_id)
        self._annotator.remove_camera(camera_id)
        self._motion_analyzer.remove_camera(camera_id)
        self._calibration_service.remove_camera(camera_id)
        self._synchronizer.remove_camera(camera_id)
        self._last_frame_seen_at.pop(camera_id, None)
        self._camera_inference_controls.pop(camera_id, None)
        self._last_active_tracks.pop(camera_id, None)
        self._last_queue_latency_ms.pop(camera_id, None)
        self._last_decode_time_ms.pop(camera_id, None)
        self._last_stream_fps.pop(camera_id, None)
        self._last_reconnect_attempts.pop(camera_id, None)
        self._metrics.set_stream_worker_up(camera_id, False)
        self._metrics.set_tracking_worker_up(camera_id, False)
        self._metrics.set_tracking_active_tracks(camera_id, 0)
        self._metrics.set_inference_queue_depth(camera_id, 0)
        identity_events = self._identity_service.remove_camera(camera_id)
        if identity_events:
            try:
                await self._dispatcher.publish_identity_events(identity_events)
            except Exception as exc:  # pylint: disable=broad-except
                self._logger.warning(
                    "Failed to publish identity cleanup events for camera %s: %s",
                    camera_id,
                    exc,
                )
        await self._inference_manager.remove_camera(camera_id)
        self._refresh_sync_group(utc_now(), None)
        self._logger.info(
            "OpenCV pipeline camera state removed: camera_id=%s discarded_frames=%s expired_identities=%s",
            camera_id,
            discarded_frames,
            len(identity_events),
        )
        self._metrics.set_active_cameras(len(self._active_cameras))
        self._metrics.set_stream_worker_count(len(self._active_cameras))
        self._metrics.set_tracking_worker_count(len(self._active_cameras))

    async def _sync_inference_controls(self, camera_records: list[CameraRecord]) -> None:
        """Apply persisted per-camera inference settings to active worker cameras."""

        if not self._settings.opencv_pipeline_enable_behavior_inference:
            for camera_id in list(self._camera_inference_controls):
                await self._inference_manager.remove_camera(camera_id)
                self._camera_inference_controls.pop(camera_id, None)
            return

        active_camera_ids = set(self._active_cameras)
        records_by_camera_id = {
            camera.id: camera for camera in camera_records if camera.id in active_camera_ids
        }
        for camera_id in list(self._camera_inference_controls):
            if camera_id not in records_by_camera_id:
                self._camera_inference_controls.pop(camera_id, None)

        for camera_id, camera in records_by_camera_id.items():
            enabled = self._resolve_camera_inference_enabled(camera)
            strategy = self._resolve_camera_inference_strategy(camera)
            current = self._camera_inference_controls.get(camera_id)

            if not enabled:
                if current is not None:
                    await self._inference_manager.remove_camera(camera_id)
                    self._camera_inference_controls.pop(camera_id, None)
                    self._logger.info(
                        "OpenCV pipeline inference disabled for camera %s via stream controls.",
                        camera_id,
                    )
                continue

            if current is None:
                await self._inference_manager.configure_stream(
                    camera_id,
                    enabled=True,
                    strategy=strategy,
                )
                self._camera_inference_controls[camera_id] = (True, strategy)
                self._logger.info(
                    "OpenCV pipeline inference enabled for camera %s with strategy=%s.",
                    camera_id,
                    strategy,
                )
                continue

            _enabled, current_strategy = current
            if current_strategy == strategy:
                continue
            await self._inference_manager.configure_stream(
                camera_id,
                strategy=strategy,
            )
            self._camera_inference_controls[camera_id] = (True, strategy)
            self._logger.info(
                "OpenCV pipeline inference strategy updated for camera %s: %s -> %s",
                camera_id,
                current_strategy,
                strategy,
            )

    def _resolve_camera_inference_enabled(self, camera: CameraRecord) -> bool:
        """Return whether inference should run for this camera."""

        inference_metadata = self._extract_inference_metadata(camera)
        raw_enabled = inference_metadata.get("enabled")
        if isinstance(raw_enabled, bool):
            return raw_enabled
        return True

    def _resolve_camera_inference_strategy(self, camera: CameraRecord) -> str:
        """Return the strategy configured for a camera, defaulting to settings."""

        inference_metadata = self._extract_inference_metadata(camera)
        raw_strategy = inference_metadata.get("strategy")
        if raw_strategy in {"vjepa_probe", "cnn_transformer"}:
            return str(raw_strategy)
        if raw_strategy is not None:
            self._logger.warning(
                "Unsupported inference strategy %r for camera %s; falling back to %s.",
                raw_strategy,
                camera.id,
                self._settings.opencv_pipeline_inference_strategy,
            )
        return self._settings.opencv_pipeline_inference_strategy

    @staticmethod
    def _extract_inference_metadata(camera: CameraRecord) -> dict[str, object]:
        """Return the nested ``stream_state.metadata.inference`` object when present."""

        inference_metadata = camera.stream_metadata.get("inference")
        if isinstance(inference_metadata, dict):
            return inference_metadata
        return {}

    async def _process_bundle(self, bundle) -> None:
        prepared_frames = []
        motion_summaries = []

        for packet in bundle.packets:
            profile = self._calibration_service.get_profile(packet.camera_id)
            processed_frame = self._preprocessor.process(packet, calibration=profile)
            calibrated_frame = self._calibration_service.undistort(
                processed_frame.working_bgr,
                profile,
            )
            world_reference_frame = self._calibration_service.align_to_world(
                calibrated_frame,
                profile,
            )
            processed_frame = self._preprocessor.refresh(
                processed_frame,
                calibrated_frame,
                world_reference_frame=world_reference_frame,
            )
            processed_frame, _transform = self._stabilizer.stabilize(processed_frame)
            motion_summary = self._motion_analyzer.analyze(processed_frame)
            prepared_frames.append(processed_frame)
            motion_summaries.append(motion_summary)

        detection_started_at = perf_counter_ns()
        detection_batches = self._detector.detect_batch(
            [processed_frame.working_bgr for processed_frame in prepared_frames]
        )
        detection_latency_ms = (perf_counter_ns() - detection_started_at) / 1_000_000.0
        self._metrics.observe_detection_latency(detection_latency_ms)

        tracked_assignments: list[tuple[object, list[object]]] = []
        tracking_total_latency_ms = 0.0
        for processed_frame, detections in zip(prepared_frames, detection_batches):
            tracking_started_at = perf_counter_ns()
            tracks = self._tracker.update(
                camera_id=processed_frame.packet.camera_id,
                stream_name=processed_frame.packet.stream_name,
                detections=detections,
            )
            tracking_total_latency_ms += (
                perf_counter_ns() - tracking_started_at
            ) / 1_000_000.0
            self._populate_world_coordinates(processed_frame.packet.camera_id, tracks)
            tracked_assignments.append((processed_frame, tracks))

        reid_latency_ms = await self._reidentifier.enrich_tracks(tracked_assignments)
        identity_events, identity_latency_ms = await self._identity_service.assign(tracked_assignments)
        self._metrics.observe_tracking_latency(
            tracking_total_latency_ms / max(len(prepared_frames), 1)
        )
        self._metrics.observe_reid_latency(reid_latency_ms)
        self._metrics.observe_identity_assignment_latency(identity_latency_ms)
        for event in identity_events:
            self._metrics.increment_tracking_identity_resolution(
                event.camera_id,
                matched_existing=event.matched_existing,
            )

        outputs: list[PipelineOutput] = []
        for processed_frame, motion_summary, detections, tracks in zip(
            prepared_frames,
            motion_summaries,
            detection_batches,
            [tracks for _processed_frame, tracks in tracked_assignments],
        ):
            camera_identity_events = [
                event
                for event in identity_events
                if event.camera_id == processed_frame.packet.camera_id
            ]
            output = PipelineOutput(
                processed_frame=processed_frame,
                annotated_bgr=processed_frame.working_bgr,
                motion=motion_summary,
                detections=detections,
                tracks=tracks,
                identity_events=camera_identity_events,
                pipeline_latency_ms=(
                    perf_counter_ns() - processed_frame.packet.monotonic_ns
                )
                / 1_000_000.0,
                detection_latency_ms=detection_latency_ms,
                tracking_latency_ms=tracking_total_latency_ms / max(len(prepared_frames), 1),
                reid_latency_ms=reid_latency_ms,
                identity_latency_ms=identity_latency_ms,
            )
            output.annotated_bgr = self._annotator.annotate(output)
            self._last_active_tracks[processed_frame.packet.camera_id] = len(tracks)
            self._metrics.increment_tracking_processed_frames(processed_frame.packet.camera_id)
            self._metrics.set_tracking_worker_up(processed_frame.packet.camera_id, True)
            self._metrics.set_tracking_active_tracks(processed_frame.packet.camera_id, len(tracks))
            self._metrics.observe_frame_processing_latency(
                processed_frame.packet.camera_id,
                output.pipeline_latency_ms,
            )
            self._metrics.observe_tracking_identity_lookup_duration(
                processed_frame.packet.camera_id,
                identity_latency_ms / 1000.0,
            )
            worker_snapshot = self._active_cameras[processed_frame.packet.camera_id].worker.health_snapshot()
            self._last_decode_time_ms[processed_frame.packet.camera_id] = worker_snapshot.decode_time_ms
            self._last_stream_fps[processed_frame.packet.camera_id] = worker_snapshot.current_fps
            self._last_reconnect_attempts[processed_frame.packet.camera_id] = worker_snapshot.reconnect_attempts
            outputs.append(output)

        if outputs:
            publish_results = await asyncio.gather(
                *(self._dispatcher.publish(output) for output in outputs),
                return_exceptions=True,
            )
            for output, result in zip(outputs, publish_results):
                if isinstance(result, Exception):
                    self._logger.warning(
                        "OpenCV pipeline output dispatch failed for camera %s: %s",
                        output.processed_frame.packet.camera_id,
                        result,
                    )
                    self._metrics.record_frame_dropped(
                        output.processed_frame.packet.camera_id,
                        reason="publish_failed",
                    )
                    self._metrics.set_stream_worker_up(
                        output.processed_frame.packet.camera_id,
                        False,
                    )
                    continue
                self._metrics.increment_tracking_published_frames(
                    output.processed_frame.packet.camera_id
                )

        published_event_keys = {
            (event.camera_id, event.local_track_id, event.event_type.value, event.occurred_at)
            for event in identity_events
            if event.camera_id in {frame.packet.camera_id for frame in prepared_frames}
        }
        remaining_events = [
            event
            for event in identity_events
            if (
                event.camera_id,
                event.local_track_id,
                event.event_type.value,
                event.occurred_at,
            )
            not in published_event_keys
        ]
        if remaining_events:
            await self._dispatcher.publish_identity_events(remaining_events)

    def _build_source_config(self, camera: CameraRecord) -> FrameSourceConfig:
        calibration_path = self._settings.opencv_pipeline_calibration_directory / f"{camera.id}.json"
        return FrameSourceConfig(
            camera_id=camera.id,
            stream_name=camera.name.replace(" ", "_").lower(),
            source_uri=build_rtsp_url_from_camera(camera),
            target_width=self._settings.opencv_pipeline_target_width,
            target_height=self._settings.opencv_pipeline_target_height,
            target_fps=self._settings.opencv_pipeline_target_fps,
            calibration_path=calibration_path if calibration_path.exists() else None,
            metadata=camera.metadata,
        )

    def _load_calibration_profile(self, source: FrameSourceConfig) -> None:
        if source.calibration_path is None:
            self._calibration_service.load_profile(source.camera_id, None)
            return
        self._calibration_service.load_profile(source.camera_id, source.calibration_path)

    def _populate_world_coordinates(self, camera_id: str, tracks: list[object]) -> None:
        for track in tracks:
            center_x = track.left + (track.width / 2.0)
            feet_y = track.top + track.height
            world_point = self._calibration_service.image_to_world(camera_id, center_x, feet_y)
            if world_point is None:
                continue
            track.world_x = world_point[0]
            track.world_y = world_point[1]

    def _refresh_sync_group(
        self,
        reference_time: datetime,
        current_camera_id: str | None,
    ) -> None:
        healthy_camera_ids = sorted(
            camera_id
            for camera_id in self._active_cameras
            if (
                current_camera_id == camera_id
                or camera_id in self._last_frame_seen_at
                and (
                    reference_time - self._last_frame_seen_at[camera_id]
                ).total_seconds()
                <= max(2.0, 5.0 / max(self._settings.opencv_pipeline_target_fps, 1.0))
            )
        )
        if not healthy_camera_ids and current_camera_id is not None:
            healthy_camera_ids = [current_camera_id]
        healthy_camera_ids_tuple = tuple(healthy_camera_ids)
        if healthy_camera_ids_tuple == self._sync_camera_ids:
            return
        self._synchronizer.close()
        self._sync_camera_ids = healthy_camera_ids_tuple
        self._synchronizer = MultiCameraSynchronizer(
            list(healthy_camera_ids_tuple),
            self._settings.opencv_pipeline_sync_tolerance_ms,
        )
        self._logger.info("OpenCV pipeline sync group updated: %s", healthy_camera_ids_tuple)
