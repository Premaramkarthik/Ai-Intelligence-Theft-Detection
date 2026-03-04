# Backend Enhancement Plan (Orchestrated)

This plan coordinates the removal of specific object filtering and proposes high-level architectural improvements for the Antigravity Vision backend.

## 🔴 Multi-Agent Coordination
This task is being orchestrated by:
1. **project-planner**: Architectural strategy and task breakdown.
2. **backend-specialist**: Implementation of detector changes and service logic.
3. **performance-optimizer**: Profiling and ensuring CPU efficiency with increased detection load.
4. **test-engineer**: Verification of detection accuracy and system stability.

---

## Proposed Changes

### 1. General Object Detection (D4)
Remove the restrictive class filtering to detect any object a person might pick up (all 80 COCO classes).

### 2. Cross-Camera Re-ID (New Requirement)
Ensure a person maintains the same ID when moving between cameras.

#### [NEW] [reid_service.py](file:///home/karthik/Downloads/pipeline_opencv/backend/services/inference/services/reid_service.py)
- Implement a feature extraction service using a Re-ID model (e.g., OSNet).
- Generate a 128/512-dim embedding for every new track.
- Store and compare embeddings in Redis using cosine similarity to assign global IDs.

### 3. Backend Architectural Suggestions (Brainstorming)

| Area | Suggestion | Why This Matters |
| :--- | :--- | :--- |
| **Accuracy** | **Implement ByteTrack** | The current tracker is a mock. Real tracking is essential for stable "Interaction" detection over time. |
| **Performance** | **OpenVINO / ONNX Export** | Since the system runs on CPU, exporting YOLO models to OpenVINO can yield a 2x-4x speedup. |
| **Logic** | **Staged D4 Trigger** | Instead of running D4 (Object Detection) every 3rd frame everywhere, run it *only* in a crop around detected person hands to save massive CPU. |
| **Reliability** | **Centralized Config Service** | Move hardcoded Redis URLs and camera settings from `.env` to a dynamic Redis-backed config service. |
| **Observability** | **Structured Trace IDs** | Add trace IDs to Redis messages so we can track a single frame from `mediabridge` → `inference` → `signaling` in logs. |

---

## 3. Verification Plan

### Automated Tests
- Run `test_detector.py` (to be created) to ensure all COCO objects are detected.
- Profile CPU usage with full 80-class detection enabled.

### Manual Verification
- Test with unconventional objects (e.g., a chair, a book) to ensure they are now labeled in the dashboard UI.
- Verify that "normal/shoplifting" classification still triggers correctly based on these new objects.
