# Inference Service: The Intelligent Core

The **Inference Service** is the brain of the pipeline. It orchestrates a multi-staged AI engine to transform raw pixels into actionable security insights using a high-efficiency model management system.

---

## 1. Multi-Stage Pipeline (D1–D5)

Every frame received from `MediaBridge` passes through five distinct stages of processing:

### D1: Human Detection & Segmentation
- **Model**: YOLO 2.6 (Ultralytics).
- **Function**: Extracts person bounding boxes and pixel-perfect masks.
- **Optimization**: Prioritizes human signals to reduce false positives in complex retail environments.

### D2: Vectorized Privacy Blur
- **Logic**: Blurs the background while keeping tracked subjects sharp.
- **Optimization**: Uses **vectorized NumPy operations** for near-instant execution, ensuring privacy compliance without impacting FPS.

### D3: Consistent Tracking
- **Algorithm**: ByteTrack / Kalman Filter.
- **Function**: Assigns and maintains unique `track_id`s for every person, even during partial occlusions.

### D4: Interaction & Proximity
- **State Logic**: Detects relationships between persons and "restricted ROIs" or items.
- **Integration**: Leverages real-time configuration from Redis (thresholds, ROI coordinates).

### D5: Asynchronous Behavior Analysis
- **Model**: EfficientNet-Transformer (Temporal).
- **Mechanism**: Triggered when interaction logic detects suspicious movement.
- **Non-Blocking**: classification runs as a background `asyncio` task, allowing the live 25+ FPS feed to remain uninterrupted.

---

## 2. Model Management & Optimization

### Singleton ModelManager
To minimize GPU memory (VRAM) overhead, the service uses a centralized **ModelManager**:
1.  **Lazy Loading**: Models are not loaded into memory until the first camera begins streaming. This allows the system to sit idle with near-zero GPU footprint.
2.  **CUDA Warm-up**: Upon first load, the manager runs "dummy" inference to initialize CUDA kernels, preventing the 1-2 second lag usually seen on the first frame.
3.  **Context Sharing**: One model instance serves all camera workers, significantly reducing VRAM fragmentation.

### Zero-Copy SHM Reads
The service uses `shared.shm.ReaderCache` to read pixels directly from system memory pointers. This eliminates expensive network serialization and local CPU copies.

---

## 3. Reliability Measures

### Lag Mitigation (Auto-Parity)
If hardware performance dips, the service implements **backlog draining**:
- If the `frames` queue exceeds **100 items**, the service flushes all stale entries and "jumps" to the newest frame to maintain real-time parity.

### Metrics & Observability
Exposes live performance data via the System Status API and Prometheus:
- **`inference_latency`**: Total time for stages D1-D4.
- **`queue_depth`**: Live monitoring of the Redis frame buffer.
- **`gpu_memory_usage`**: Real-time VRAM telemetry.
