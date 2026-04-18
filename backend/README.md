# OpenCV Edge AI Backend

This backend contains the current production path for the RTSP camera AI system:

- FastAPI control plane for camera CRUD, validation, health, metrics, websocket fanout, and inference controls.
- Standalone OpenCV edge worker in `backend/main.py`.
- Modular OpenCV pipeline in `src/opencv_pipeline`.
- Kafka event bridge for `camera.frames`, `camera.tracking.updates`, `camera.ai_results`, and `identity.events`.
- Triton-backed behavioral inference services in `src/services/inference`.
- Milvus-backed identity matching in `src/services/tracking/identity`.
- PostgreSQL migrations and SQL files under `scripts/`.
- Prometheus/Grafana/Loki/Alloy observability assets under `observability/`.

The active frame-processing flow is:

```text
Camera/RTSP
  -> OpenCV VideoCapture
  -> bounded frame buffer
  -> multi-camera timestamp synchronizer
  -> preprocessing
  -> calibration / undistortion / homography projection
  -> optical-flow stabilization
  -> motion analysis
  -> batched YOLO detection
  -> Roboflow ByteTrack tracking
  -> body ReID embedding
  -> Milvus identity assignment
  -> Kafka + Triton ingress + websocket bridge
```

Architecture details and verification references are documented in
`docs/opencv_pipeline_architecture.md`.

## Entrypoints

- API server: `src/main.py`
- Edge worker: `main.py`
- Docker stack: `docker-compose.yaml`

## Important Runtime Assets

- YOLO detector weights: `yolo26n.pt`
- Triton model repository: `model_repository/triton`
- ReID weights: `src/services/tracking/reid/weights/mobilenetv2_bottleneck_wts.pt`
- SQL migrations: `scripts/migrations`
- SQL query files: `scripts/sql`

Generated runtime data under `runtime/` is intentionally not part of source cleanup.

## Verification

Run the focused backend suite:

```bash
backend/.venv/bin/pytest -q backend/tests/opencv_pipeline backend/tests/test_tracking_updates.py backend/tests/test_tracking_kafka_service.py backend/tests/test_observability_metrics.py backend/tests/test_camera_service.py backend/tests/test_inference_services.py backend/tests/test_websocket_fanout.py backend/tests/test_bytetrack_tracker.py backend/tests/test_trackers_supervision_adapter.py backend/tests/test_milvus_batch_resolve.py backend/tests/test_shared_embedding_service.py backend/tests/test_config.py backend/tests/test_ffmpeg_utils.py backend/tests/test_retry_utils.py backend/tests/test_kafka_event_consumer.py
```

Run the frontend production build:

```bash
cd frontend
npm run build
```
