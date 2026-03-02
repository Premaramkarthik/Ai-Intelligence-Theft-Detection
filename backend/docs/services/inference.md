# Inference Service: The Intelligent Core

The **Inference Service** is the most complex component of the pipeline. It orchestrates multiple AI models and state machines to transform raw pixels into actionable security insights.

---

## 1. Multi-Stage Pipeline (D1–D5)

Every frame received from `MediaBridge` passes through five distinct stages of processing:

### D1: Detection & Segmentation
- **Model**: YOLOv8n-seg (quantized to FP16/INT8).
- **Output**: Bounding boxes for people and high-resolution segmentation masks.
- **Optimization**: We use segmentation masks for both privacy and as a filter for item interaction.

### D2: Optimized Privacy Blur
- **Logic**: Background components are blurred while tracked persons remain sharp.
- **Optimization**: This is implemented using **vectorized NumPy operations**. Instead of iterating through segments, we create a combined binary mask and use `cv2.GaussianBlur` on the inverse, then blend using `np.where`.
- **Resolution Stability**: Automatically handles cases where the detector returns masks at a different resolution than the source frame.

### D3: Object Tracking
- **Algorithm**: IOU-based matching (or ByteTrack).
- **Stability**: Ensures that a person walking through the frame retains their unique `track_id`. This is critical for the temporal classification in D5.

### D4: Interaction State Machine
- **State Logic**: `IDLE` → `WATCHING` (Near item) → `TRIGGERED` (Item moved/concealed).
- **Proximity**: Compares person bounding boxes with ROI coordinates defined in Redis.

### D5: Asynchronous Action Classification
- **Model**: EfficientX3D.
- **Temporal Buffer**: Maintains a rolling window (default 16 frames) of past video frames.
- **Non-Blocking Execution**: Since video classification is computationally expensive (~7s), it is triggered as an **asynchronous background task**. This allows the main pipeline to continue processing frames at 25+ FPS while the classification runs.
- **Concurrency Control**: Ensures only one classification task is active per camera at a time to prevent GPU memory overflow.

---

## 2. Performance & Reliability

### Zero-Copy Reads
The service never "receives" image data over the network. It receives a `FramePointer` and uses the `libs.shared.shm.ReaderCache` to read the pixels directly from the system's shared memory.

### Self-Healing (Lag Mitigation)
If the processing time per frame exceeds the arrival rate, the `frames` queue will grow. The inference service includes a **drain-on-backlog** logic:
- If `queue_length > 100`, it purges all oldest messages and jumps to the most recent frame.
- This ensures that alerts are always based on the latest possible information.

### Metrics & Monitoring
The service exposes a `/metrics` endpoint for Prometheus, tracking:
- **Inference Latency**: Time taken for D1-D4.
- **Queue Depth**: Real-time backlog size.
- **Processed Frames**: Total count since startup.
- **Dropped Frames**: Count of frames skipped due to backlog.
