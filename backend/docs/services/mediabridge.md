# MediaBridge Service: The Ingestion Gateway

The **MediaBridge** service is responsible for high-performance video ingestion. It acts as the "eyes" of the pipeline, transforming inconsistent camera streams into a standardized, zero-latency shared memory buffer.

---

## 1. Core Responsibilities

- **Multi-Source Ingestion**: Pulls video from RTSP, RTMP, or local USB webcams.
- **Process Isolation**: Each camera is managed by an independent child process (`CameraWorker`), ensuring that a network hang on one camera doesn't freeze the rest of the system.
- **Normalization**: Resizes and converts incoming frames into a standardized BGR format for the inference engine.
- **Seeding**: On startup, it automatically seeds default ROI and thresholds into Redis for any newly discovered cameras.

---

## 2. Technical Workflow

1.  **Discovery**: On boot, the supervisor reads the `CAMERA_SOURCES` configuration.
2.  **Worker Launch**: For each source, it spawns a `CameraWorker`.
3.  **Capture Loop**:
    -   Requests a frame from `cv2.VideoCapture`.
    -   Writes the frame into the next available slot in the **Shared Memory Ring Buffer**.
    -   Generates a `FramePointer` containing the Slot ID and precise capture timestamp.
4.  **Inference Trigger**: Pushes the `FramePointer` to the Redis `frames` queue.
5.  **Health Heartbeat**: Updates a Redis key every few seconds to signal that the ingestion is active.

---

## 3. Zero-Latency via Shared Memory

To achieve high frame rates (30 FPS+ across multiple cameras), MediaBridge uses the `libs.shared.shm.RingBufferWriter`. This allows frames to be passed to the `Inference` service without ever leaving the system's RAM or requiring expensive serialization.

---

## 4. Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CAMERA_SOURCES` | `None` | Comma-separated list of URLs/Indices. |
| `FRAME_WIDTH` | `1280` | Target horizontal resolution. |
| `FRAME_HEIGHT` | `720` | Target vertical resolution. |
| `SHM_SLOTS_PER_CAM` | `32` | Size of the rolling buffer in memory. |
| `RTSP_TRANSPORT` | `tcp` | Transport protocol (tcp/udp) for RTSP streams. |

---

## 🛠️ Operational Commands
If running without Docker, start the service using:
```bash
PYTHONPATH=. ./.venv/bin/python3 services/mediabridge/main.py
```
Check `logs/mediabridge.log` for ingestion metrics and connectivity status.
