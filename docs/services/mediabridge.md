# MediaBridge Service

The **MediaBridge** service is the "eyes" of the pipeline. It is responsible for high-performance video ingestion and providing a zero-latency frame buffer for downstream processing.

## Purpose
- Ingest video streams from multiple sources simultaneously.
- Provide a high-throughput, zero-copy transport mechanism (Shared Memory) for inference.
- Manage camera metadata and health status.

## Technologies Used
- **OpenCV**: Used for robust video capture (`cv2.VideoCapture`). It supports RTSP, RTMP, and local Webcam devices.
- **Python Multiprocessing**: Each camera runs in its own process (or thread managed by a supervisor) to ensure that the bottleneck of one camera (e.g., network latency) doesn't affect others.
- **Shared Memory (SHM)**: Utilizes `multiprocessing.shared_memory` to create a ring-buffer of raw NumPy arrays. This allows the Inference service to read frames directly without CPU-intensive serialization.
- **Redis**: Acts as the signaling layer, storing "pointers" to the latest frames in SHM.

## How it works
1. **Source Connection**: Connects to RTSP URLs or Webcam IDs defined in `CAMERA_SOURCES`.
2. **Frame Capture**: Pulls raw bytes from the stream.
3. **SHM Write**: Writes the frame bytes into a pre-allocated slot in the Shared Memory ring buffer.
4. **Redis Notify**: Pushes a `FramePointer` (Camera ID + Slot ID + Timestamp) to a Redis List (`frames`) to trigger the Inference service.

## Configuration
- `CAMERA_SOURCES`: Comma-separated list of sources.
- `FRAME_WIDTH` / `FRAME_HEIGHT`: Target resolution for normalization.
- `SHM_SLOTS_PER_CAM`: Size of the ring buffer (default 32).
