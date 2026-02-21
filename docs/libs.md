# Shared Libraries (`libs/`)

The `libs/` directory contains the core infrastructure and business logic shared across all services. This centralization ensures that critical components like Shared Memory handling and data contracts are consistent throughout the entire pipeline.

---

## 🏗️ Folder: `libs/shared/`

### 1. `shm/` (Zero-Copy Transport)
This is the performance backbone of the project.
- **`ring_buffer.py`**: Implements a high-performance ring buffer using `multiprocessing.shared_memory`.
    - **`RingBufferWriter`**: Used by `MediaBridge` to write raw BGR frames into slots.
    - **`RingBufferReader`**: Used by `Inference` and `Signaling` to read frames based on slot IDs.
    - **`ReaderCache`**: A thread-safe utility ensuring services maintain a persistent, cached connection to SHM segments, preventing the overhead of re-attaching for every frame.

### 2. `types/` (Data Contracts)
Standardizes the communication between services.
- **`models.py`**: Contains the single source of truth for our data models:
    - **`FramePointer`**: The lightweight Redis payload (Camera ID, Slot ID, Timestamp, Trace ID).
    - **`BBox`**: Pixel-perfect bounding box with built-in IOU math.
    - **`Detection`**: Individual frame results (BBox, Confidence, Class).
    - **`DetectionEvent`**: The object pushed to the `persistence_queue`.

### 3. `core/` (System Configuration)
- **`settings.py`**: Manages environment variable loading via `pydantic-settings`. Every service uses this to access `.env` variables with full type-safety.

### 4. `logging/` (Structured Observability)
- **`logger.py`**: Configures `structlog` for the entire system.
- **Features**:
    - **JSON Output**: Optimized for ingestion by Logstash/Loki.
    - **Contextual Injection**: Automatically tags every log line with the service name and camera ID when available.

### 5. `utils/` (General Helpers)
- Shared helper functions for time formatting, path resolution, and Prometheus metric initialization.

---

## 💡 Why Centralize Logic in `libs/`?
- **Zero-Bugs IPC**: By using the same `FramePointer.to_bytes()` and `.from_bytes()` logic in both sender and receiver, we eliminate "broken contract" bugs.
- **Performance Consistency**: Optimizations made to the `RingBuffer` immediately benefit every service in the pipeline.
- **Atomic Types**: Shared types like `BBox` allow us to use the same logic for intersection-over-union tracking and UI overlay rendering.
