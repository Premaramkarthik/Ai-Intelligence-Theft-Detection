# OpenCV Edge Pipeline Architecture

## Verification Baseline

This implementation was designed against OpenCV official documentation and GitHub reference implementations, then reconciled with the actual runtime available in this repo.

Verified references:

- OpenCV `videoio` / `VideoCapture`: https://docs.opencv.org/4.x/javadoc/org/opencv/videoio/VideoCapture.html
- OpenCV `core`: https://docs.opencv.org/4.x/javadoc/org/opencv/core/Core.html
- OpenCV `imgproc`: https://docs.opencv.org/4.x/javadoc/org/opencv/imgproc/Imgproc.html
- OpenCV `calib3d`: https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html
- OpenCV `video` optical flow: https://docs.opencv.org/4.x/db/d7f/tutorial_js_lucas_kanade.html
- OpenCV background subtraction / `MOG2`: https://docs.opencv.org/4.x/javadoc/org/opencv/video/BackgroundSubtractorMOG2.html
- OpenCV G-API imgproc module: https://docs.opencv.org/4.x/d2/d00/group__gapi__imgproc.html
- OpenCV G-API design notes: https://github.com/opencv/opencv/wiki/Graph-API
- OpenCV Lucas-Kanade sample: https://raw.githubusercontent.com/opencv/opencv/4.x/samples/python/lk_track.py
- Ultralytics YOLO reference repo: https://github.com/ultralytics/ultralytics
- FoundationVision ByteTrack reference repo: https://github.com/FoundationVision/ByteTrack
- Torchreid / OSNet reference repo: https://github.com/KaiyangZhou/deep-person-reid
- OpenVINO Open Model Zoo multi-camera tracking demo docs: https://docs.openvino.ai/2023.3/omz_demos_multi_camera_multi_target_tracking_demo_python.html
- OpenVINO Open Model Zoo demo source: https://raw.githubusercontent.com/openvinotoolkit/open_model_zoo/master/demos/multi_camera_multi_target_tracking_demo/python/multi_camera_multi_target_tracking_demo.py

Runtime validation note:

- The local Python runtime exposes `cv2.gapi`, but the installed `cv2.bgsegm` and `cv2.videostab` namespaces are placeholder-only in this environment. Because of that, the production path implemented here uses documented, stable primitives from `videoio`, `imgproc`, `video`, and `calib3d`, with optional contrib selection hooks where available.

## True Pipeline

The implemented edge pipeline follows the required stage order:

`Capture -> Buffer -> Preprocess -> Calib3D -> Stabilize -> Motion -> Detect -> Track -> ReID -> Identity -> Output`

Concrete runtime chain:

1. `VideoCaptureWorker` reads RTSP/device streams with `cv2.VideoCapture`.
2. `FrameBuffer` absorbs burstiness and applies backpressure policy.
3. `MultiCameraSynchronizer` aligns frames by monotonic timestamp window.
4. `FramePreprocessor` performs resize, BGR->RGB conversion, grayscale extraction, normalization, and low-light flagging.
5. `CalibrationService` applies `undistort`, optional homography warping, and image-to-world projection.
6. `OpticalFlowStabilizer` applies Lucas-Kanade feature tracking plus `estimateAffinePartial2D`.
7. `MotionAnalyzer` computes dense Farneback flow and foreground ratio from background subtraction.
8. `YOLOBatchDetector` runs batched Ultralytics detection.
9. `ByteTrackStage` maintains per-camera local track identity with Roboflow ByteTrack.
10. `BodyReIdentifier` batches person chips into the appearance embedding model.
11. `IdentityAssignmentService` resolves global identities through Milvus and emits lifecycle events.
12. `OutputDispatcher` publishes tracking updates, frame events, identity events, and inference ingress samples.

## Architecture Diagram

```text
Camera / RTSP
    |
    v
VideoCaptureWorker (per camera)
    |
    v
FrameBuffer ----> MultiCameraSynchronizer
                        |
                        v
                OpenCvPipelineRuntime
                        |
        +---------------+-------------------------------+
        |               |               |               |
        v               v               v               v
   Preprocess      Calibration      Stabilize        Motion
        |               |               |               |
        +---------------+---------------+---------------+
                        |
                        v
                 YOLOBatchDetector
                        |
                        v
                   ByteTrackStage
                        |
                        v
                 BodyReIdentifier
                        |
                        v
              IdentityAssignmentService
                        |
                        v
                  OutputDispatcher
        +---------------+----------------------------+
        |               |                            |
        v               v                            v
tracking.updates   camera.frames                identity.events
        |               |                            |
        +---------------+----------------------------+
                        |
                        v
                   Kafka topics
                        |
        +---------------+--------------------+
        |                                    |
        v                                    v
InferenceManager / Triton             StreamEventConsumer
        |                                    |
        v                                    v
 PostgreSQL + camera.ai_results        WebSocketManager -> frontend
```

## Module Responsibilities

| Module | Responsibility | Implementation |
| --- | --- | --- |
| `ingestion` | Camera/video acquisition and reconnect handling | `src/opencv_pipeline/ingestion/capture.py` |
| `buffering` | Queue backpressure and multicamera time alignment | `src/opencv_pipeline/buffering/*` |
| `preprocessing` | Resize, color conversion, normalization, low-light flag | `src/opencv_pipeline/preprocessing/processor.py` |
| `calibration` | Intrinsics, undistortion, homography, world projection | `src/opencv_pipeline/calibration/service.py` |
| `stabilization` | LK sparse optical flow + affine stabilization | `src/opencv_pipeline/stabilization/stabilizer.py` |
| `motion` | Farneback motion + background subtraction | `src/opencv_pipeline/motion/analyzer.py` |
| `detection` | Batched YOLO inference | `src/opencv_pipeline/detection/yolo.py` |
| `tracking` | Per-camera ByteTrack lifecycle | `src/opencv_pipeline/tracking/stage.py` |
| `reid` | Batched body embedding extraction | `src/opencv_pipeline/reid/stage.py` |
| `identity` | Milvus matching, create/update/merge/expire events | `src/opencv_pipeline/identity/service.py` |
| `output` | Frame annotation, Kafka payloads, tracking fanout | `src/opencv_pipeline/output/publisher.py` |
| `runtime` | Distributed orchestration and camera refresh | `src/opencv_pipeline/runtime.py` |

## Distributed Integration

Edge processing layer:

- The new standalone worker entrypoint is `backend/main.py`.
- It bootstraps PostgreSQL access, Kafka producer, Triton-backed `InferenceManager`, and the OpenCV pipeline runtime.
- It reads active camera inventory from PostgreSQL via `CameraService`.
- It publishes three edge topics:
  - `camera.frames`
  - `camera.tracking.updates`
  - `identity.events`
- Inference results continue to flow through `camera.ai_results`.

Backend/API layer:

- `src/main.py` remains the FastAPI control plane.
- `StreamEventConsumer` consumes Kafka topics and rebroadcasts them through `WebSocketManager`.
- `/streams/ws/updates` is now a Kafka-backed event websocket.
- `/streams/{camera_id}/inference` controls Triton inference activation per camera.

## Message Schemas

Kafka schemas are implemented in code, not ad hoc JSON:

- `camera.tracking.updates`: existing `TrackingKafkaEventPayload`
- `camera.frames`: `CameraFrameKafkaEventPayload`
- `identity.events`: `IdentityKafkaEventPayload`
- `camera.ai_results`: existing inference payloads

Schema principles:

- camera-scoped keying
- UTC timestamps on every event
- explicit bounding boxes
- global identity fields separated from local track ids
- optional JPEG preview only for `camera.frames`

## Identity System Design

Embedding path:

1. ByteTrack emits local person tracks.
2. The ReID stage crops each person patch from the stabilized working frame.
3. Embeddings are batched and passed to Milvus.
4. `MilvusIdentityStore.batch_resolve()` returns either a matched identity or a new one.

Lifecycle handling:

- `create`: no prior local assignment and Milvus did not match an existing global identity
- `update`: same local track keeps the same global identity, or a local track attaches to an already-known global identity
- `merge`: a local track was previously mapped to one global id and is later remapped to another
- `expire`: no updates for longer than the configured TTL

Persistence:

- Global embeddings and metadata live in Milvus.
- Behavioral inference events are already persisted in PostgreSQL.
- Identity lifecycle events are emitted to Kafka for downstream persistence/analytics.

## Multi-Camera Fusion Logic

Temporal synchronization:

- `MultiCameraSynchronizer` aligns frames using monotonic timestamps and a configurable tolerance window.
- The runtime maintains a dynamic sync group so a disconnected camera does not permanently stall healthy cameras.

Spatial alignment:

- Optional homographies map image coordinates into a shared plane.
- Track footpoints are projected into world coordinates for downstream reasoning.

Cross-camera identity linking:

- Appearance embeddings are resolved against a shared Milvus collection.
- Synchronization plus shared-world coordinates provide the hooks needed for future geometry-aware conflict gating.
- The design follows the same tuple-of-frames pattern used by the Open Model Zoo multicamera reference.

## Performance Strategy

- Batched YOLO inference across synchronized frames
- Batched ReID embedding extraction across all tracks in a bundle
- Dedicated capture thread per camera
- Queue-based backpressure with drop policy control
- Async Kafka publication and async Triton ingress
- GPU-capable Ultralytics and ReID execution
- Metrics hooks for queue depth, frame latency, active tracks, Kafka health, and dependency health

Latency target:

- The code is structured for sub-40 ms edge latency at modest camera counts with GPU acceleration.
- Exact SLA still depends on camera FPS, model size, GPU availability, and Triton model throughput.

## Failure Handling

- Camera disconnect: `VideoCaptureWorker` reconnects with exponential backoff.
- Frame bursts: `FrameBuffer` enforces bounded queues with configurable drop policy.
- Missing calibration: pipeline continues without undistortion/homography.
- Low light: preprocessing flags dark frames so downstream policy can react.
- Tracker churn or occlusion: ByteTrack keeps short-lived lost tracks and identity is refreshed through ReID.
- Missing contrib bindings: runtime falls back to stable core/video implementations.
- Kafka outage: producer/consumer health is surfaced through `/health` and Prometheus.

## Folder Structure

```text
backend/
  main.py
  docs/opencv_pipeline_architecture.md
  src/opencv_pipeline/
    ingestion/
    buffering/
    preprocessing/
    calibration/
    stabilization/
    motion/
    detection/
    tracking/
    reid/
    identity/
    output/
    runtime.py
```

## Implementation Roadmap

Completed in this change:

- modular pipeline package
- standalone edge worker bootstrap
- Kafka frame and identity topics
- FastAPI websocket/Kafka bridge
- Milvus-backed global identity lifecycle
- focused tests for buffering, synchronization, and identity lifecycle

Recommended next increments:

1. Replace the retained MobileNet embedding model with a dedicated OSNet export if OSNet standardization is required.
2. Add PostgreSQL persistence for `identity.events`.
3. Add geometry-aware identity conflict resolution using world-coordinate constraints.
4. Externalize calibration management and camera sync groups into admin APIs.
5. Add benchmark fixtures for per-stage latency under real RTSP load.
