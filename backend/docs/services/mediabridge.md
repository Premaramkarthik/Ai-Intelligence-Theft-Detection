# MediaBridge Service: The Ingestion Gateway

The **MediaBridge** service is responsible for high-performance video ingestion. It acts as the "eyes" of the pipeline, transforming inconsistent camera streams into a standardized, zero-latency shared memory buffer.

---

## 1. Core Responsibilities

- **Multi-Source Ingestion**: Pulls video from RTSP, HTTP, or local USB webcams.
- **Robustness**: Uses piped **FFmpeg** processes for RTSP streams, providing significantly better network resilience than standard OpenCV.
- **Process Isolation**: Each camera is managed by an independent `CameraWorker` task.
- **Normalization**: Standardizes incoming frames to a unified resolution (default 720p) and BGR format.

---

## 2. Technical Workflow

1.  **Dynamic Discovery**: The supervisor monitors Redis for new camera connection requests initiated via the Signaling API (`/api/camera/connect`).
2.  **Health Supervisor**: The main loop continuously audits active workers. If a worker task stops (due to process crash or network failure), the supervisor automatically restarts it within 5 seconds.
3.  **Ingestion Modes**:
    -   **Webcam**: Uses standard `cv2.VideoCapture`.
    -   **RTSP**: Spawns an FFmpeg sub-process using TCP transport and auto-hardware acceleration for maximum stability.
4.  **SHM Write**: Frames are written into a **Shared Memory Ring Buffer** for zero-copy access by the inference engine.
5.  **Notification**: Pushes a `FramePointer` to the Redis `frames` queue to trigger the detection pipeline.

---

## 3. High-Reliability RTSP (FFmpeg)

Unlike simple capture libraries, our FFmpeg implementation handles jitter and packet loss professionally:
-   **Transport**: Enforces TCP to prevent UDP-related frame corruption ("smearing").
-   **Acceleration**: Leverages `hwaccel auto` to reduce CPU load during stream decoding.
-   **Resilience**: Piped raw video output is validated by the `CameraWorker` to ensure data integrity.

---

## 4. Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `FRAME_WIDTH` | `1280` | Target horizontal resolution for SHM. |
| `FRAME_HEIGHT` | `720` | Target vertical resolution for SHM. |
| `SHM_SLOTS_PER_CAM` | `32` | Depth of the rolling buffer per camera. |
| `POLL_INTERVAL` | `5.0` | Supervisor frequency for health audits (seconds). |

---

## 🛠️ Management
The service is primarily managed via the **Signaling API**.
- To add a camera: `POST /api/camera/connect`.
- To monitor health: `GET /api/status`.
- To view logs: Check `logs/mediabridge.log` for per-worker connectivity status.
