# Shared Libraries (`libs/`)

The `libs/` directory contains all core logic that is shared across multiple services. This centralized approach ensures consistency, reduces bug surface, and simplifies maintenance.

## Folder: `libs/shared/`

The primary library is `libs.shared`, which is organized by functionality:

### 1. `core/` (Settings & Configuration)
- **`settings.py`**: A centralized Pydantic-Settings model that loads environment variables from `.env`. It provides type-safety and default values for the entire project.
- **`config.py`**: Contains the `ConfigManager`, which handles live updates from Redis (e.g., changing camera ROI during runtime).

### 2. `logging/` (Structured Logging)
- Implements a unified logging configuration using `structlog`.
- All services emit logs in **JSON format**, which includes standard fields like `timestamp`, `level`, `service_name`, and `camera_id` for easy ingestion into log aggregators (Loki, Elasticsearch).

### 3. `shm/` (Shared Memory IPC)
- The backbone of the zero-copy pipeline. 
- Implements a `RingBuffer` using Python's `multiprocessing.shared_memory`. 
- Provides `SHMWriter` (used by MediaBridge) and `SHMReader` (used by Inference/Signaling).

### 4. `types/` (Data Models)
- Defines all inter-process communication (IPC) contracts using Pydantic.
- **`Detection`**: Bounding box + class info.
- **`FramePointer`**: Metadata about a frame slot in SHM.
- **`Prediction`**: The final output of the Inference service.

### 5. `utils/` (Helpers)
- General purpose utilities for time conversion, image processing (OpenCV wrappers), and metrics collection (Prometheus).

---

## Why this structure?
1. **DRY (Don't Repeat Yourself)**: Shared logic like Redis connection handling or logging setup is written once and imported everywhere.
2. **Type Safety**: Using Pydantic models in `libs/` ensures that if the `Prediction` model changes, every service using it is immediately aware through type-checking.
3. **Simpler Containerization**: All services mount or copy the `libs/` folder, ensuring they all run on the exact same infrastructure code.
