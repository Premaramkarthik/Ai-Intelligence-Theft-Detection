"""End-to-end runtime for the modular OpenCV edge processing pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter_ns

from src.core.config import Settings
from src.core.logger.logger import get_logger
from src.models.camera import CameraRecord, CameraStatus
from src.observability.metrics import MetricsRecorder, NullMetricsRecorder
from src.opencv_pipeline.buffering.frame_buffer import FrameBuffer
from src.opencv_pipeline.buffering.synchronizer import MultiCameraSynchronizer
from src.opencv_pipeline.calibration.service import CalibrationService
from src.opencv_pipeline.contracts import FrameSourceConfig, PipelineOutput, utc_now
from src.opencv_pipeline.detection.yolo import YOLOBatchDetector
from src.opencv_pipeline.identity.service import IdentityAssignmentService
from src.opencv_pipeline.ingestion.capture import VideoCaptureWorker
from src.opencv_pipeline.motion.analyzer import MotionAnalyzer
from src.opencv_pipeline.output.publisher import FrameAnnotator, OutputDispatcher
from src.opencv_pipeline.preprocessing.processor import FramePreprocessor
from src.opencv_pipeline.reid.stage import BodyReIdentifier
from src.opencv_pipeline.stabilization.stabilizer import OpticalFlowStabilizer
from src.opencv_pipeline.tracking.stage import ByteTrackStage
from src.services.camera.camera_service import CameraService
from src.services.inference.manager import InferenceManager
from src.services.tracking.identity.milvus_store import MilvusIdentityStore
from src.services.tracking.reid.embedder import TrackingReIdEmbedder
from src.services.tracking.updates import FanoutTrackingUpdatePublisher, InferenceIngressPublisher
from src.services.tracking_kafka.service import TrackingKafkaProducerService
from src.utils.ffmpeg import build_rtsp_url_from_camera


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
        metrics_recorder: MetricsRecorder | None = None,
    ) -> None:
        self._settings = settings
        self._camera_service = camera_service
        self._inference_manager = inference_manager
        self._metrics = metrics_recorder or NullMetricsRecorder()
        self._logger = get_logger(__name__)
        self._frame_buffer = FrameBuffer(
            maxsize=settings.opencv_pipeline_frame_buffer_size,
            drop_policy=settings.opencv_pipeline_drop_policy,
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
            metrics_recorder=self._metrics,
        )
        self._identity_service = IdentityAssignmentService(
            identity_store,
            identity_ttl_seconds=settings.opencv_pipeline_identity_ttl_seconds,
        )
        publishers = [tracking_kafka_producer.publisher()]
        if settings.opencv_pipeline_enable_behavior_inference:
            publishers.append(InferenceIngressPublisher(inference_manager))
        self._tracking_update_publisher = FanoutTrackingUpdatePublisher(publishers)
        self._annotator = FrameAnnotator()
        self._dispatcher = OutputDispatcher(
            self._tracking_update_publisher,
            frame_publisher=tracking_kafka_producer.json_publisher(
                settings.kafka_topic_camera_frames
            ),
            identity_event_publisher=tracking_kafka_producer.json_publisher(
                settings.kafka_topic_identity_events
            ),
            annotated_stream_suffix=settings.tracking_stream_suffix,
            include_previews=settings.opencv_pipeline_publish_frame_previews,
            jpeg_quality=settings.opencv_pipeline_preview_jpeg_quality,
        )
        self._active_cameras: dict[str, _ActiveCamera] = {}
        self._last_frame_seen_at: dict[str, datetime] = {}
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
        self._running = True

    async def stop(self) -> None:
        """Stop all capture workers and close downstream clients."""

        if not self._running and not self._active_cameras:
            return
        self._running = False
        for camera_id in list(self._active_cameras):
            await self._remove_camera(camera_id)
        self._identity_service.close()

    async def run_forever(self) -> None:
        """Run the pipeline until ``stop()`` is called."""

        await self.start()
        refresh_started_at = utc_now()
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

                packet = await self._frame_buffer.get()
                if packet.camera_id not in self._active_cameras:
                    continue

                self._last_frame_seen_at[packet.camera_id] = packet.captured_at
                self._metrics.record_frame_received(packet.camera_id)
                self._refresh_sync_group(packet.captured_at, packet.camera_id)
                bundle = self._synchronizer.submit(packet)
                if bundle is None:
                    continue
                await self._process_bundle(bundle)
        finally:
            await self.stop()

    async def refresh_cameras(self) -> None:
        """Refresh active cameras from PostgreSQL and start/stop workers as needed."""

        camera_records = await self._camera_service.list_all_camera_records()
        target_sources = {
            camera.id: self._build_source_config(camera)
            for camera in camera_records
            if camera.status == CameraStatus.active
        }

        for camera_id in list(self._active_cameras):
            if camera_id in target_sources:
                if self._active_cameras[camera_id].source == target_sources[camera_id]:
                    continue
            await self._remove_camera(camera_id)

        for camera_id, source in target_sources.items():
            if camera_id in self._active_cameras:
                continue
            worker = VideoCaptureWorker(
                source,
                self._frame_buffer,
                retry_initial_delay_seconds=(
                    self._settings.opencv_pipeline_capture_retry_initial_delay_seconds
                ),
                retry_max_delay_seconds=(
                    self._settings.opencv_pipeline_capture_retry_max_delay_seconds
                ),
            )
            worker.start()
            self._active_cameras[camera_id] = _ActiveCamera(source=source, worker=worker)
            if self._settings.opencv_pipeline_enable_behavior_inference:
                await self._inference_manager.configure_stream(
                    camera_id,
                    enabled=True,
                    strategy=self._settings.opencv_pipeline_inference_strategy,
                )
            self._load_calibration_profile(source)

        self._refresh_sync_group(utc_now(), None)

    async def _remove_camera(self, camera_id: str) -> None:
        active_camera = self._active_cameras.pop(camera_id, None)
        if active_camera is None:
            return
        active_camera.worker.stop()
        discarded_frames = self._frame_buffer.discard_camera(camera_id)
        self._tracker.remove_camera(camera_id)
        self._stabilizer.remove_camera(camera_id)
        self._motion_analyzer.remove_camera(camera_id)
        self._calibration_service.remove_camera(camera_id)
        self._synchronizer.remove_camera(camera_id)
        self._last_frame_seen_at.pop(camera_id, None)
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
            await self._dispatcher.publish(output)
            self._metrics.observe_frame_processing_latency(
                processed_frame.packet.camera_id,
                output.pipeline_latency_ms,
            )
            self._metrics.increment_tracking_processed_frames(
                processed_frame.packet.camera_id,
                1,
            )
            self._metrics.increment_tracking_published_frames(
                processed_frame.packet.camera_id,
                1,
            )
            self._metrics.set_tracking_active_tracks(
                processed_frame.packet.camera_id,
                len(tracks),
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
        self._sync_camera_ids = healthy_camera_ids_tuple
        self._synchronizer = MultiCameraSynchronizer(
            list(healthy_camera_ids_tuple),
            self._settings.opencv_pipeline_sync_tolerance_ms,
        )
        self._logger.info("OpenCV pipeline sync group updated: %s", healthy_camera_ids_tuple)
