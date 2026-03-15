# Engineering Diligence Report: `pipeline_opencv` v3

**Audit Date:** 2026-03-14 | **Auditor:** Claude Code | **Branch:** `v3`

---

## 1. Executive Summary

**What this software does:** Real-time shoplifting detection platform for retail environments. Five Python microservices ingest RTSP/webcam video streams, run TensorRT-accelerated YOLO detection + ByteTrack tracking + CNN+Transformer behavior classification, and dispatch Telegram alerts when shoplifting behavior is detected. A Next.js frontend provides live stream viewing with detection overlays and incident history.

**Business problem:** Retail loss prevention via automated camera surveillance, replacing or augmenting human security monitoring.

**Architecture vs. product goal fit:** The architecture *ambition* is correct — event-driven microservices, zero-copy SHM transport, GPU-accelerated inference, Redis-backed messaging. The gap is that several critical pipeline stages are either stubs, mocked, or broken. The product cannot actually detect shoplifting in its current state for reasons detailed in Section 8.

**Current classification:** **Serious Prototype** — the scaffolding is production-grade in intent but the core detection logic has a fatal flaw that makes it functionally incorrect. The infrastructure around the AI pipeline is well-designed; the AI pipeline itself is not yet real.

---

### Final Verdict

| Dimension | Assessment |
|---|---|
| **Strongest parts** | Redis-only inter-service messaging; SHM ring buffer design; TensorRT wrapper for classifier; Telegram circuit breaker; Docker-compose structure; FastAPI lifespan lifecycle |
| **Weakest parts** | D3 interaction detector is a mock (see §8.1); ReID uses blocking KEYS scan; ObjectDetector ignores tracker_id; Signaling reads SHM but lacks `ipc: host`; no DB partition automation |
| **Top technical risks** | False-positive storm from broken interaction trigger; JWT in localStorage; KEYS O(n) redis scan in hot path; zero test coverage on inference logic |
| **Top opportunities** | Architecture is sound enough to fix with targeted effort; Redis Streams already in place for fan-out; TensorRT models already integrated |

---

## 2. Product Understanding

**What it does:** Monitors camera feeds for shoplifting behavior. When a person appears in frame and interacts with items (per a proximity state machine), a clip is fed to a behavior classifier. If the classifier returns `shoplifting` above a confidence threshold, a Telegram alert fires and the incident is stored in PostgreSQL.

**Who the user is:** Retail store security staff / store managers. They view live streams in the browser, see bounding boxes and incident banners, and receive Telegram alerts.

**Core workflow:**
1. Admin connects camera (RTSP URL or webcam) via dashboard
2. System ingests video, writes frames to SHM ring buffer
3. Inference pulls frame pointers from Redis queue, runs detection
4. If person-item interaction detected, runs behavior classification
5. If shoplifting detected, fires Telegram alert + writes to DB
6. Frontend shows live stream with overlays and incident history

**Does the code support this vision?** Partially. Steps 1, 2, 4 (partially), 5, and 6 work. Step 3 (person-item proximity detection) is explicitly mocked. Step 4's interaction trigger fires for every person present for N frames, not just those near items.

---

## 3. Repo Structure Audit

```
pipeline_opencv/
├── backend/                 [sound — clear service separation]
│   ├── docker-compose.yml   [good structure, one critical missing flag]
│   ├── services/            [good — 5 services clearly separated]
│   │   ├── inference/       [good design, broken logic inside]
│   │   ├── mediabridge/     [solid]
│   │   ├── signaling/       [solid routing, one SHM access violation]
│   │   ├── alerting/        [solid]
│   │   └── persistence/     [thin but clean]
│   ├── shared/              [good — contracts, settings, SHM, DB in one place]
│   ├── scripts/schema.sql   [contains migration guards mixed with DDL — messy]
│   ├── tests/               [3 unit tests total — dangerously thin]
│   └── models/              [not in git — good]
│
├── frontend/src/
│   ├── app/                 [4 pages — sparse but clean]
│   ├── components/          [functional but underdeveloped]
│   ├── hooks/               [good pattern]
│   └── stores/              [Zustand — appropriate]
│
└── start.cmd / stop.cmd     [Windows dev launcher — not production]
```

**Issues:**
- `backend/shared/db/session.py` is duplicated at `backend/services/persistence/db/session.py` (identical file)
- `backend/services/inference/ml/engines/__init__.py` references engines but `shoplifting_model.py` was deleted (D status in git)
- `prompt.md` and `r.md` are committed to repo root (developer notes, should be gitignored)
- `backend/.venv` is committed — should be in `.gitignore`

**Repo maturity score: 5.5/10**

The structure is intentional and well-named. Deductions: `.venv` in repo, duplicate db session, 3 tests total, dev files committed, no `CONTRIBUTING.md` or runbook.

---

## 4. Architecture Audit

### System Components

```
[Browser] ←──WebSocket/REST──→ [Signaling :9000]
                                      │
                               [Redis :6379] ←──── ALL services
                                      │
    ┌─────────────────────────────────┼──────────────────────────────┐
    │                                 │                              │
[MediaBridge]              [Inference GPU]                  [Alerting]
 reads cameras              blpop "frames"                  xread "stream:incidents"
 writes SHM                 reads SHM                       sends Telegram
 rpush "frames"             publishes "telemetry:{id}"      publishes MQTT
                            xadd "stream:incidents"
                                                           [Persistence]
                                                            xread "stream:incidents"
                                                            writes PostgreSQL
```

### Architecture Assessment

**Pattern:** Event-driven microservices over Redis. Correct choice for latency-sensitive streaming workloads.

**Clean?** Mostly yes. No direct HTTP calls between services. All coupling is through Redis keys and channels. Contract definitions live in `shared/types/events.py`.

**Modular?** Yes — each service has a clear single responsibility.

**Tightly coupled?** Three hidden coupling points:
1. **SHM naming convention** — `cam_{id}_ring` is known by MediaBridge (writer), Inference (reader), and Signaling (reader). Any rename breaks all three silently.
2. **Redis key space** — Undocumented in code. `frame_ptr:*`, `camera_status:*`, `config:*`, `camera_sources`, `frames`, `telemetry:*`, `reid:embeddings:*`, `logs` — 8 distinct key namespaces with no formal registry.
3. **Signaling reads SHM directly** — `camera_service.py:grab_jpeg()` accesses SHM via `ReaderCache`. This requires Signaling to run on the same host as MediaBridge. The docker-compose **does not set `ipc: host` for the signaling service**, meaning `GET /api/camera/{id}/snapshot` silently fails in Docker with no error except "No frame available."

**What breaks first under scale?**
1. Redis single node — all 5 services fail simultaneously
2. The `frames` Redis list — single list for all cameras, no per-camera partitioning
3. The `KEYS` scan in ReID — O(N) blocking operation on every frame per tracked person

**Missing for real-world deployment:**
- Redis Sentinel/Cluster
- Per-camera frame queues
- Automated DB partition management
- No nginx/TLS in front of Signaling

---

## 5. Frontend Audit

### Structure
- **4 pages:** `/` (redirect), `/login`, `/dashboard`, `/history`
- **Key components:** `StreamCard`, `ConnectionModal`, `CameraGrid`, `SystemStatusBanner`
- **State:** Zustand (`useAuthStore`, `useCameraStore`) + TanStack Query for REST

### Issues Found

**Security:**
- JWT stored in `localStorage` — vulnerable to XSS. Should use `httpOnly` cookie.
- WebSocket connects with `?token=<jwt>` as a query parameter. This token appears in server access logs, Nginx logs, and browser history.

**UX Logic Failures:**
- `useCamerasSynchronizer.ts:41` — hardcodes `status: 'online'` for ALL cameras fetched from API. The actual camera status (`camera_status:{id}` Redis key) is never read. Users cannot distinguish a misconfigured/offline camera from a working one.
- No token refresh logic. `jwt_expire_minutes` defaults to 60. After expiry, the WebSocket closes (code 1008) and the user is silently logged out mid-session. No warning before expiry, no refresh endpoint.
- `StreamCard` WebSocket is NOT reconnected after close. If the backend restarts, the card shows "Waiting for backend stream" indefinitely until the user refreshes.

**Canvas/Image rendering:**
- Canvas is hardcoded at `width={1280} height={720}`. On monitors with non-16:9 aspect ratios or when the card is smaller, bounding box coordinates are offset. The canvas CSS fills the parent div but the coordinate space is always 1280×720 — correct only if frames are exactly 1280×720.

**Frontend architecture score: 5/10**
**Frontend UX maturity score: 4/10**
**Frontend maintainability score: 6/10**

`Detection`, `Incident`, and `CameraStreamMessage` interfaces are defined locally in `StreamCard.tsx` rather than a shared types file. Backend schema changes break frontend silently.

---

## 6. Backend Audit

### API Structure
FastAPI + dependency injection pattern is clean. JWT via `OAuth2PasswordBearer` is standard. Rate limiting via `slowapi` exists.

### Critical Issues

**1. `camera.py` imports from `mediabridge` directly (`L14`):**
```python
from services.mediabridge.sources.sources import validate_source
```
The Signaling service imports from MediaBridge. This hard couples two services that should be fully independent. If MediaBridge dependencies (OpenCV, etc.) are not installed in the Signaling container, this import fails at startup.

**2. Auth route exposes admin credentials directly:**
Single hardcoded admin account. No multi-user, no roles, no audit trail of who logged in.

**3. `jwt_secret` empty string default:**
```python
jwt_secret: str = os.getenv("JWT_SECRET", "")
```
In development, JWT signing key is an empty string. `_validate_security_settings()` only throws if `app_env != "development"`. So in dev, tokens are signed with `""` — trivially forgeable.

**4. CORS origins from env string splitting:**
If `CORS_ORIGINS` env contains a trailing comma, an empty string enters the origins list. FastAPI's CORSMiddleware behavior with `""` as an allowed origin is undefined.

**5. No request body size limits.** Large `CameraConnectRequest` payloads could exhaust memory.

**6. Config route writes directly to Redis without validation:**
Any authenticated user can write arbitrary inference parameters for any camera. No schema validation on config updates.

**Backend architecture score: 6/10**
**API design score: 6/10**
**Production-readiness score: 3/10**

---

## 7. End-to-End Data Flow Audit

```
Camera → [MediaBridge CameraWorker]
  1. cv2.read() → resize to 1280×720
  2. SHM write → slot_id + generation
  3. FramePointer JSON → rpush("frames")
  4. redis.set("frame_ptr:{id}", ptr)
  ↓
Redis list "frames"
  ↓
[Inference blpop("frames")]
  5. FramePointer.from_bytes()
  6. ReaderCache.get_reader() → RingBufferReader.read()
     ↑ RACE: generation may have been overwritten if queue backlog > 32 slots
  7. ItemInteractionDetector.update()
     ↑ BUG: triggers on EVERY person after interaction_frames, no proximity check
  8. TemporalBuffer.push(frame)
  9. if should_classify() → asyncio.create_task(_run_classification)
     ↑ BUG: BehaviorClassifier._infer() is synchronous CUDA — blocks event loop
  10. Publish FrameTelemetryMessage → "telemetry:{id}"
  ↓
[Signaling WS /ws/camera/{id}]
  11. Loop at camera_stream_fps: grab_jpeg from SHM + grab_metadata from Redis
  12. base64 encode JPEG + merge metadata → send to browser
  ↓
[Browser StreamCard]
  13. Decode base64 → img.src
  14. drawDetections on canvas (hardcoded 1280×720)
  ↓
[Incident path]
  15. xadd("stream:incidents", payload)
  16. [Alerting] xread → TelegramService.send_shoplifting_alert()
  17. [Persistence] xread → asyncpg INSERT INTO detection_events
```

**Where failures happen:**
- Step 6: SHM slot overwritten before read (if inference backlog > 32 frames). The generation check catches it but the frame is silently dropped.
- Step 7: False positive storm — everyone triggers classification.
- Step 9: CUDA blocking event loop — inference workers stall.
- Step 11: Signaling reads SHM but lacks `ipc: host` in Docker.
- Step 17: DB partition only covers through April 2026. May 2026 writes fail.

**Is the flow robust?** No. Two of the 17 steps contain fundamental correctness bugs.

---

## 8. AI / ML / Edge Pipeline Audit

### 8.1 — D3 Stage: BROKEN (Most Critical Bug)

**File:** `backend/services/inference/services/interaction.py:54`

```python
# Mock logic: if we detected an item near hands, increment state
# In real code, we'd check distance between hands and items
self._states[tid] = self._states.get(tid, 0) + 1
if self._states[tid] >= self._interaction_frames:
    self._should_classify = True
```

This is explicitly labeled "Mock logic" in the source code. The actual hand-item proximity check is not implemented. Every person that appears for `interaction_frames` consecutive frames (default: 5 at 15 FPS = **every person visible for 0.3 seconds**) triggers behavior classification. In a busy store, this means the behavior classifier runs on nearly every frame for every person, defeating the purpose of the interaction gate entirely and creating a massive false-positive pipeline.

**Real-world consequence:** The system will send Telegram alerts for every customer in the store. It will immediately lose operator trust on day one.

### 8.2 — D2 Stage: Per-Camera Tracking Broken

**File:** `backend/services/inference/ml/engines/object_detector.py:57`

```python
def detect_and_track(self, frame: np.ndarray, tracker_id: str = "default") -> DetectionResult:
    del tracker_id  # ← tracker_id is deleted immediately
    try:
        results = self._model.track(frame, persist=True, ...)
```

YOLO's `track(persist=True)` maintains an internal tracker state. With `tracker_id` deleted and never passed, all cameras share the same ByteTrack state within the ModelManager singleton. Track IDs bleed across cameras — person `#1` on camera A can be the same internal tracker ID as person `#1` on camera B. The `ItemInteractionDetector` per-camera state isolation (`CameraRuntimeState`) is undermined because the track IDs are globally contaminated.

### 8.3 — ReID: O(N) Blocking Redis KEYS Scan

**File:** `backend/services/inference/services/reid_service.py:51`

```python
keys = await self.redis.keys(f"{self.redis_key_prefix}*")
```

`KEYS *` in Redis is O(N) across the entire keyspace. Comment reads: "MVP: Key scanning. Production: RediSearch HNSW." This is called per tracked person per frame — in async context, blocking Redis until all keys are scanned. With 100 tracked persons and 1000 stored embeddings, this executes 100 blocking KEYS calls per inference cycle. The comment acknowledges this is MVP-only, but the code ships to production without the fix.

### 8.4 — ReID: Random Embedding Fallback

**File:** `backend/services/inference/services/reid_service.py:86`

```python
if self.model is None:
    vec = np.random.rand(576).astype(np.float32)
    return vec / np.linalg.norm(vec)
```

If the ReID model (MobileNetV3) fails to load, the fallback returns a **random normalized vector**. This means persons are randomly matched across cameras — producing entirely incorrect global IDs with no error visible to the operator. The proper behavior is to disable ReID and log a clear error.

### 8.5 — Behavior Classifier: Synchronous CUDA in Async Task

**File:** `backend/services/inference/ml/engines/behavior_classifier.py:160-195`

`_infer()` performs synchronous CUDA operations including `cudaStreamSynchronize(stream)` which **blocks until GPU is done**. `classify()` calls `_infer()` directly. In `pipeline.py:209`:

```python
task = asyncio.create_task(
    self._run_classification(ptr, clip, detections, redis, behavior_classifier)
)
```

This creates a coroutine task, but `_run_classification` calls `await classifier.classify(clip)` which calls the synchronous `_infer()`. CUDA `cudaStreamSynchronize` **blocks the Python thread** — and since asyncio runs on a single thread, this blocks the entire inference event loop during GPU execution. Must be wrapped in `asyncio.to_thread()`.

### 8.6 — Model Manager: Lazy Loading Race

`ModelManager` exposes `get_detector()` and `get_behavior_classifier()` as lazy getters. With `INFERENCE_GPU_WORKERS > 1`, multiple workers share the same `ModelManager` instance. If two workers call `get_detector()` simultaneously before the detector is loaded, both may try to initialize TensorRT simultaneously — likely causing a CUDA context conflict or duplicate engine load.

### 8.7 — DB Partition: Hard-Coded Through April 2026

**File:** `backend/scripts/schema.sql:31-37`

```sql
CREATE TABLE IF NOT EXISTS detection_events_2026_03 ...
CREATE TABLE IF NOT EXISTS detection_events_2026_04 ...
```

No partition for May 2026 onwards. PostgreSQL declarative partitioning raises `ERROR: no partition of relation "detection_events" found for row` when data falls outside defined ranges. Incidents in May 2026 will fail to persist silently (persistence service may swallow the exception).

### ML Pipeline Summary

| Dimension | Score |
|---|---|
| ML pipeline design | 3/10 |
| Edge deployment readiness | 5/10 |
| Inference reliability | 3/10 |

**Top 10 AI layer weaknesses:**
1. D3 proximity detector is a mock — system doesn't actually detect interaction
2. ByteTrack tracker ID shared across all cameras (tracker_id deleted)
3. Behavior classifier blocks async event loop (synchronous CUDA in coroutine)
4. ReID uses KEYS O(N) scan per frame per person
5. ReID returns random embeddings on model load failure
6. No warmup validation — model loaded but not verified against a test input
7. `classify()` not thread-safe — single CUDA context, single stream, called from multiple potential workers
8. Adaptive skip logic adjusts globally but stale `last_tracks` are returned during skipped frames — person counts can be stale for up to 10 frames
9. `clip` passed to classifier contains raw BGR frames (no ROI crop to person bbox) — classifier sees entire scene not the person
10. No calibration interface — confidence thresholds set once in env, no per-model tuning workflow

---

## 9. Performance and Scalability Audit

### Immediate Issues

**Single `frames` Redis list for all cameras:**
With 4 cameras at 15 FPS each, 60 frame pointers/sec enter a shared list. A single inference worker processes them in FIFO order. If camera A produces a burst, camera B's frames queue up behind it. Stale frames are then dropped at read time (stale generation). Effect: one slow camera starves others.

**Redis as message bus for video telemetry:**
`FrameTelemetryMessage` is published to `telemetry:{camera_id}` pub/sub AND set to `telemetry:latest:{camera_id}` on every processed frame. At 15 FPS × 4 cameras = 60 Redis writes/sec plus pub/sub fan-out. Fine now but doesn't scale to 50+ cameras without Redis Cluster.

**base64 JPEG over WebSocket:**
For 1280×720 at 80% quality, a JPEG is ~100KB, base64-encoded ≈ 133KB. At 15 FPS: **2MB/sec per camera stream per browser tab**. For 4 cameras × 2 staff = 16MB/sec backend → browser bandwidth. This will saturate a typical office connection with 3 cameras.

**`asyncio.sleep` in `ReaderCache`:**
```python
time.sleep(1)  # blocks event loop
```
`ReaderCache.get_reader()` uses `time.sleep(1)` (blocking) in a 3-retry loop. Called from an async coroutine, this blocks the entire event loop for up to 3 seconds on first SHM attach.

### Scale Scenarios

| Scenario | Expected behavior |
|---|---|
| 10 concurrent users viewing 1 camera | Each user opens a WebSocket; Signaling runs 10 loops at 15 FPS each. 10 × 15 × ~133KB = 20MB/sec backend writes. Manageable. |
| 10 cameras, 1 inference worker | Single BLPOP loop processes 150 frames/sec. With 50ms inference per frame = 5 FPS effective throughput. 10 cameras produce 150 FPS demand → 30 FPS backlog per second → queue saturates in seconds → mass stale frame drops. |
| 100 cameras | Redis `frames` list overwhelmed. Per-camera queue partitioning required. ReID KEYS scan scans tens of thousands of keys per frame → Redis timeout. |
| Long-running execution | `CameraRuntimeState._camera_states` dict grows unbounded as new cameras connect and disconnect. Old states are never evicted. |
| Redis restart | All 5 services lose connectivity simultaneously. No reconnect logic in MediaBridge main. |

---

## 10. Reliability and Failure Mode Audit

| Failure | Current Behavior | Risk | Recommended Safeguard |
|---|---|---|---|
| Redis restart | All 5 services crash or hang | **CRITICAL** | Redis Sentinel + reconnect with backoff in each service |
| Inference worker crash | Frames accumulate in Redis list, no consumer | **HIGH** | Health check endpoint; supervisor auto-restart |
| MediaBridge restart | SHM blocks destroyed mid-inference; `frame_ptr:*` keys deleted on startup | **HIGH** | SHM lifecycle fence; inference handles `FileNotFoundError` gracefully |
| DB partition expiry (May 2026) | Incidents silently fail to persist | **HIGH** | Automated partition creation via pg_partman or cron job |
| Model file missing | Service crash at startup with `FileNotFoundError` | **MEDIUM** | Pre-flight check script; health endpoint reports model status |
| CUDA OOM | TensorRT raises; `detect_and_track` catches `Exception` and returns empty result — silent | **HIGH** | Explicit CUDA OOM handling; exponential backoff; alert |
| Camera RTSP stream EOF | `CameraWorker` reconnects with exponential backoff — correct | Low | Already handled |
| WebSocket client disconnect | Signaling loop silently catches `WebSocketDisconnect` — correct | Low | Already handled |
| Incident duplicate (multi-worker) | Redis BLPOP pops atomically — correct | Low | Already safe |
| JWT secret empty in production | `_validate_security_settings()` catches this if `app_env != "development"` | **HIGH** | Fail hard on startup regardless of env |
| Partial SHM write (generation race) | Second generation check after copy catches it | Low | Already guarded |
| `detect_and_track` silent exception | Returns empty `DetectionResult()` — appears as "no persons detected" | **MEDIUM** | Separate detection failure counter metric |
| Behavior classifier CUDA block | Blocks entire async event loop | **HIGH** | Wrap in `asyncio.to_thread()` |
| PgAdmin exposed publicly | Default email is developer's personal email | **MEDIUM** | Remove from production compose or restrict to internal network |

---

## 11. Security Audit

### Critical

**C1. JWT stored in `localStorage` (XSS risk):**
`useAuthStore.ts:23` — `localStorage.setItem(TOKEN_KEY, nextToken)`. If any XSS vulnerability exists (injected ad script, CDN compromise, Markdown injection), the auth token is stolen instantly. Use `httpOnly` cookie with `SameSite=Strict`.

**C2. WebSocket token as query parameter:**
`StreamCard.tsx:53` — token appended to WebSocket URL. Query parameters are logged by every proxy, CDN, and web server in the path. JWT appears in browser history, server access logs, and any network capture.

**C3. `jwt_secret` defaults to empty string:**
In development (the common case during testing), all JWTs are signed with `""`. Any request with a token signed by `""` will verify successfully. There is no protection in dev against forged tokens.

### High

**H1. Prometheus `/metrics` exposed without authentication:**
`main.py:81` — `application.mount("/metrics", metrics_app)`. No `verify_jwt` dependency. Returns internal system metrics to any unauthenticated caller. Reveals camera count, incident rates, frame processing latencies.

**H2. RTSP credentials stored in Redis plaintext:**
RTSP URLs commonly contain credentials (`rtsp://user:pass@host`). These are stored raw in `camera_sources` hash. If Redis is accessible, RTSP credentials are exposed.

**H3. PgAdmin default credentials committed:**
`docker-compose.yml:54` — `PGADMIN_DEFAULT_EMAIL: premaramkarthik99@gmail.com` — hardcoded developer personal email. `PGADMIN_DEFAULT_PASSWORD: admin`. PgAdmin is exposed on port 5050 with a known default password.

**H4. No RTSP URL validation beyond connection test:**
`camera.py:68` — an attacker can provide internal network URLs for SSRF — scanning internal hosts via the camera connect endpoint.

**H5. `INFERENCE_GPU_WORKERS` not validated:**
If set to a large value, spawns N concurrent tasks sharing one GPU — likely causing CUDA OOM.

### Medium

**M1.** Admin credentials compared in plaintext.
**M2.** No confirmed rate limit on auth endpoint.
**M3.** Logs may contain Redis URLs with passwords.
**M4.** No HSTS / security headers.
**M5.** `allow_credentials=True` in CORS combined with wildcard origins in dev sends cookies to any origin.

### Low

**L1.** `camera_id` not validated as alphanumeric — used in Redis key construction; potential key injection.
**L2.** Evidence URI stored in DB but never verified — placeholder for future path traversal if file serving is added naively.

---

## 12. Observability and Debuggability Audit

### What exists
- Structured JSON logging via `shared/logging/logger.py`
- Redis pub/sub log forwarding
- Prometheus metrics per service on separate ports (9100-9104)
- Per-frame latency histogram (`inference_latency`)
- Frames dropped counter
- `telemetry:latest:{camera_id}` as debug snapshot

### What is missing

**No correlation IDs end-to-end:** `trace_id` is an 8-character UUID prefix (`str(uuid4())[:8]`). Not propagated to Telegram alert messages or PostgreSQL writes in `metadata`. You cannot trace an incident from alert back to the originating frame in logs. 8-char prefix has ~1% collision probability at 10K events.

**No health/readiness endpoints for most services:** Only Signaling has a `/health` route. MediaBridge, Inference, Alerting, and Persistence have no HTTP server for health checks beyond Prometheus.

**No model health metric:** No metric tracking classifier inference failures, stale model, or GPU memory pressure beyond `update_gpu_memory()`.

**No incident rate metric:** No Prometheus counter for incidents fired, false-positive rate, or alert suppression by circuit breaker.

**No WebSocket connection count metric:** Cannot know how many browser clients are active.

**Q: If a bug happens in production, how hard is it to diagnose?** Hard. Logs are structured but `trace_id` truncation (8 chars) means high collision probability.

**Q: If inference quality drops, would we know?** No. There is no metric for classification output distribution.

**Q: If latency rises slowly over time, would the system reveal it?** Partially. `inference_latency` histogram exists, but no alerting rule, no Grafana dashboard, no SLO specified.

---

## 13. Code Quality Audit

### Positives
- Consistent use of `from __future__ import annotations`
- Pydantic v2 for all wire contracts
- Dataclasses for internal types
- Type hints throughout backend
- `get_settings()` LRU-cached singleton — correct

### Issues

**Dead/stub code:**
- `interaction.py:54` — explicitly labelled "Mock logic" with TODO comment
- `object_detector.py:57` — `del tracker_id` (parameter discarded immediately)
- `reid_service.py:86` — random embedding fallback
- `models.py:DetectionEvent` — defined but "not currently used in main path"

**Inconsistent patterns:**
- `settings.py` uses `os.getenv()` directly inside `BaseSettings` class body (bypasses pydantic-settings env loading mechanism — the `os.getenv` calls run at class definition time, before `SettingsConfigDict` processes `.env` file)
- Logger naming: some files use `log = get_logger(...)`, others use `logger = get_logger(...)` — minor but inconsistent
- `reid_service.py` imports are ordered incorrectly (standard library after third-party)

**Giant concerns:**
- `pipeline.py` is the god object for inference — model management, config loading, ReID, frame processing, telemetry publishing, classification all in one class (300+ lines)
- `behavior_classifier.py:_infer()` manages raw CUDA memory directly — complex, fragile, not abstracted

**Missing contracts:**
- No interface/protocol for `BaseSource` beyond the class itself
- No type for Redis key namespaces — keys like `"telemetry:latest:{id}"` are raw strings scattered across files

**Code quality score: 6/10**
**Maintainability score: 5/10**

---

## 14. Testing Audit

### Current state
- **3 unit tests** in `test_inference_isolation.py`
- **1 integration test** in `test_telegram_alert.py`
- **0 tests** for: ObjectDetector, BehaviorClassifier, ReIDService, MediaBridge, Signaling routes, Alerting, Persistence, Frontend

### What is dangerously untested
1. The interaction trigger (which is broken — a test would have caught this)
2. YOLO integration (engine load, detect_and_track output)
3. SHM ring buffer under concurrent read/write
4. Redis Streams consumer group acknowledgment
5. JWT token validation (expired, tampered, wrong algorithm)
6. Camera connect flow end-to-end
7. DB persistence under partition boundary crossing
8. BehaviorClassifier CUDA execution path

### What bugs are slipping through
- The mock interaction logic would immediately fail a "person near item should trigger classification but person far from item should not" test
- The `del tracker_id` bug is untested
- The random ReID fallback is undetected

### Testing Roadmap

**Must add immediately:**
- Test that `ItemInteractionDetector.update()` only triggers when person bbox overlaps with item bbox within `hand_dist_px`
- Test that `detect_and_track` produces isolated track IDs per camera
- JWT auth test: expired token → 401, valid token → 200
- SHM ring buffer concurrency test (writer + reader in threads)

**Should add next:**
- Integration test: `POST /camera/connect` → MediaBridge picks up → inference worker receives frame
- Incident flow: mock inference output → Redis Stream → Alerting consumes → Telegram mock called
- DB persistence: incident written → `GET /api/events` returns it

**Optional but valuable:**
- Load test: 4 cameras × 30s → measure frame drop rate
- Chaos test: kill Redis mid-run, verify services reconnect

---

## 15. Deployment / DevOps / Production Readiness Audit

### Docker Issues

1. **`ipc: host` missing on `signaling` service.** `camera_service.py:grab_jpeg()` accesses SHM. Without `ipc: host`, the snapshot endpoint always returns 503 in Docker.

2. **No `depends_on` with health check for inference.** Inference depends on Redis but `depends_on: [redis]` fires as soon as the container starts, before Redis is healthy.

3. **`pgadmin` in production compose.** PgAdmin is a development tool. It should be in a separate `docker-compose.override.yml` or removed from production compose.

4. **`evidence-data` volume created but never written to.** The persistence service defines this volume, but no code writes evidence to `/data/evidence`. Dead volume.

5. **`start.cmd` is a Windows dev launcher.** Not a production deployment tool. Starts services as background processes in cmd.exe without process supervision.

6. **`requirements.txt` and `pyproject.toml` both exist** — two sources of truth for dependencies. `requirements.txt` may drift from `uv.lock`.

### Can this be reliably deployed today?
In Docker on a Linux host with NVIDIA GPU: mostly yes for the media ingestion and API layers. The AI pipeline would produce massively incorrect results due to the interaction mock. The snapshot endpoint would fail. DB writes would fail in May 2026.

---

## 16. Architecture Smells and Technical Debt

### Urgent

**1. D3 Interaction Gate is a stub**
Business risk: System fires alerts on every customer. Destroys operator trust immediately.
Technical risk: Classification runs at full rate, GPU constantly busy.
Fix: Implement actual bbox distance calculation between person wrist/hand keypoints and item bounding boxes.

**2. ObjectDetector discards tracker_id**
Business risk: Multi-camera deployments produce wrong track IDs.
Technical risk: Per-camera state isolation breaks down.
Fix: Pass `tracker_id` to YOLO's `track()` using `tracker` parameter for separate ByteTrack instances.

**3. Signaling accesses SHM without `ipc: host`**
Business risk: Snapshot endpoint silently fails in Docker.
Fix: Add `ipc: host` to signaling service OR serve JPEG snapshots via a different path (Redis-cached JPEG bytes written by MediaBridge).

### Important

**4. ReID uses KEYS scan** — Fix: Use `HSCAN` or Redis Search with vector similarity.
**5. BehaviorClassifier blocks event loop** — Fix: Wrap `_infer()` in `asyncio.to_thread()`.
**6. DB partitions only through April 2026** — Fix: Implement `pg_partman` with auto-partition creation.
**7. JWT in localStorage + WS token in query param** — Fix: Use `httpOnly` cookie; WebSocket subprotocol or header for auth.
**8. `os.getenv()` in `BaseSettings` class body** — Fix: Use pydantic-settings field declarations only.

### Later

**9.** Duplicate `db/session.py` — merge into shared package only.
**10.** No Redis key namespace registry — document or codify key namespaces.
**11.** `InferencePipeline` god class — split into pipeline orchestrator + per-stage processors.
**12.** No partition automation — consider `pg_partman`.
**13.** Random ReID fallback — disable ReID on model load failure instead.

---

## 17. Brutal Truth Section

**What looks impressive:**
- The overall architecture is unusually mature for a solo/small-team project. Event-driven via Redis Streams, TensorRT integration, SHM ring buffer with generation counters, circuit breaker for Telegram, Prometheus metrics per service, Pydantic v2 contracts — this level of infrastructure thinking is rare.
- `BehaviorClassifier` with raw CUDA memory management and dynamic tensor binding is legitimately sophisticated.
- The `CameraRuntimeState` per-camera isolation pattern is correct and shows architectural discipline.

**What is pretending to be production-ready but isn't:**
- The `ItemInteractionDetector` has a comment saying "Mock logic" in the D3 stage of a product whose entire value proposition depends on D3. This is the core detection engine and it doesn't work. The rest of the pipeline — TensorRT models, SHM transport, Redis Streams, Telegram alerts — is all serving a broken trigger.
- ReID is using `KEYS *` pattern with a comment acknowledging it's an MVP approach, but it runs in the hot path on every frame per tracked person. This will collapse under any meaningful load.
- The BehaviorClassifier blocks the asyncio event loop during GPU inference. The entire inference service freezes during classification — the most critical path.

**What parts are likely to fail in production:**
- D3 will create an alert storm within minutes of deployment in any real store.
- DB writes fail silently after April 2026.
- The snapshot endpoint silently returns 503 in Docker.
- ReID KEYS scan degrades to multi-second Redis locks under moderate load.

**What needs redesign instead of patching:**
- `ItemInteractionDetector.update()` needs real spatial computation, not a frame counter. This requires actual hand/wrist keypoint extraction from YOLO pose model OR a proper proximity heuristic using person bbox lower half vs item bbox.
- The camera stream delivery architecture (SHM → base64 JPEG over WebSocket) works for 1-4 cameras but needs rethinking for scale.

**What would scare a CTO or enterprise buyer:**
1. The D3 stub comment in source code — "In real code, we'd check distance"
2. Developer personal email hardcoded in `docker-compose.yml`
3. JWT signed with empty string in development
4. 3 unit tests total
5. Database partitions expire in April 2026

---

## 18. Scoring Dashboard

| Dimension | Score |
|---|---|
| Product clarity | 7/10 |
| Repo structure | 5.5/10 |
| Frontend design | 5/10 |
| Backend design | 6/10 |
| API quality | 6/10 |
| AI pipeline design | 3/10 |
| Scalability | 4/10 |
| Reliability | 4/10 |
| Security | 3/10 |
| Observability | 5/10 |
| Code quality | 6/10 |
| Testing | 1/10 |
| Deployment readiness | 4/10 |
| **Production readiness overall** | **3/10** |

**Final classification: Serious Prototype**

The infrastructure ambition and the surrounding architecture exceed what this classification usually implies. This is not a student demo — it's a properly-designed system that happens to have critical business logic unimplemented and critical security hardening missing. With targeted fixes to the D3 stage, CUDA blocking, ReID, and JWT handling, this moves to **Strong MVP** in 2-3 weeks of focused work.

---

## 19. Top 20 Fixes (Priority Order)

### Immediate (must fix before any demo or real deployment)

| # | Issue | Why it matters | Impact | Difficulty | Action |
|---|---|---|---|---|---|
| 1 | D3 interaction gate is a mock | System fires alerts on every customer — unusable | Critical | Medium | Implement bbox proximity check: person lower-half centroid vs. item bbox within `hand_dist_px` pixels |
| 2 | `del tracker_id` in ObjectDetector | Multi-camera track IDs collide | Critical | Low | Remove the `del`; use separate ByteTrack instances per camera via `tracker` parameter |
| 3 | BehaviorClassifier blocks event loop | Inference service freezes during GPU inference | Critical | Low | Wrap `_infer()` in `asyncio.to_thread()` |
| 4 | Signaling missing `ipc: host` in Docker | Snapshot endpoint always returns 503 | High | Trivial | Add `ipc: host` to signaling service in docker-compose, OR move snapshot generation into MediaBridge |
| 5 | DB partitions expire April 2026 | Incidents fail to persist from May 2026 | High | Low | Add partitions through Dec 2026 immediately; implement `pg_partman` for automation |
| 6 | ReID random embedding fallback | Silent incorrect cross-camera identity | High | Low | On model load failure: set `self.model = None`, log error, return `None` from `extract_features`, skip ReID entirely |
| 7 | JWT stored in localStorage | XSS token theft | High | Medium | Migrate to `httpOnly` cookie with `SameSite=Strict`; update Signaling to set/clear cookie |

### Short-term (before operator pilot)

| # | Issue | Why it matters | Impact | Difficulty | Action |
|---|---|---|---|---|---|
| 8 | ReID uses `KEYS *` scan | O(N) Redis block per frame per person | High | Medium | Replace with `HSCAN` cursor scan or Redis Search vector index |
| 9 | WebSocket token in query param | JWT logged in access logs | High | Low | Use WebSocket subprotocol header or first-message auth handshake |
| 10 | PgAdmin hardcoded credentials | Open DB admin UI in production | High | Trivial | Move pgadmin to `docker-compose.override.yml`; remove personal email from source |
| 11 | Prometheus `/metrics` unauthenticated | Exposes system internals | Medium | Low | Add IP whitelist middleware or move to internal port |
| 12 | `os.getenv()` in `BaseSettings` class body | `.env` file values ignored for these fields | Medium | Low | Replace with pydantic-settings field declarations with `default=` |
| 13 | Token refresh mechanism missing | Users silently logged out after 60 minutes | Medium | Medium | Add `POST /auth/refresh` endpoint; implement silent refresh in frontend |
| 14 | Camera status always `'online'` in frontend | Operators can't distinguish offline cameras | Medium | Low | Read `camera_status:{id}` from API and reflect real status |
| 15 | No WebSocket reconnect in StreamCard | Feed goes dead on backend restart | Medium | Low | Add exponential backoff reconnect logic |

### Medium-term (before general availability)

| # | Issue | Why it matters | Impact | Difficulty | Action |
|---|---|---|---|---|---|
| 16 | No inference pipeline tests | Broken D3 undetected; any regression invisible | High | Medium | Add integration tests for interaction trigger logic and classifier output |
| 17 | Signaling imports MediaBridge directly | Cross-service coupling; deployment entanglement | Medium | Medium | Move `validate_source` to `shared/` or use a Redis-based camera validation flow |
| 18 | `InferencePipeline` god class | Hard to test and modify | Medium | Medium | Extract `TelemetryPublisher`, `IncidentEmitter`, `ConfigLoader` as separate classes |
| 19 | No per-camera frame queues | Camera starvation under mixed load | Medium | Medium | Replace single `frames` list with `frames:{camera_id}` per-camera lists |
| 20 | Single Redis node — no HA | Complete system outage on Redis restart | Critical at scale | High | Add Redis Sentinel; implement reconnect backoff in all service Redis clients |

---

## 20. Refactor Roadmap

### Phase 1 — Stabilize (1–2 weeks)

**Goal:** Make the system functionally correct and deployable without causing an alert storm.

- Fix D3: Implement actual hand-item proximity detection (person bbox lower quadrant vs. item bbox distance)
- Fix `del tracker_id`: Proper per-camera ByteTrack instances
- Fix CUDA blocking: `asyncio.to_thread()` around `_infer()`
- Fix `ipc: host` in docker-compose for signaling
- Fix DB partitions: Add through Dec 2026 + pg_partman setup
- Fix ReID fallback: Disable instead of randomize
- Remove developer personal email from docker-compose
- Add `min_length=32` validation on `jwt_secret`

**Exit criteria:** System can run for 24h in a store environment without false-positive alert storm.

---

### Phase 2 — Clean Architecture (2–4 weeks)

**Goal:** Eliminate hidden coupling and stubs; make the codebase maintainable.

- Decompose `InferencePipeline` into focused classes
- Remove Signaling → MediaBridge import; move `validate_source` to shared or change approach
- Merge duplicate `db/session.py`
- Remove `DetectionEvent` dead code
- Codify Redis key namespace as constants in `shared/`
- Add per-camera frame queues (`frames:{camera_id}`)
- Replace `KEYS *` in ReID with `HSCAN` cursor
- Add frontend shared types file instead of per-component interface duplication
- Implement WebSocket reconnect in `StreamCard`
- Implement token refresh

---

### Phase 3 — Production Hardening (4–8 weeks)

**Goal:** Add reliability, security, and observability layers.

- Security: JWT → `httpOnly` cookie; WS auth via first-message handshake
- Security: Move `/metrics` behind auth or internal network
- Security: SSRF protection for RTSP URL validation (allowlist/denylist for private CIDRs)
- Observability: Full end-to-end `trace_id` propagation (16-char minimum, added to Telegram alerts and DB rows)
- Observability: Incident rate metrics; classification distribution metrics
- Observability: Health/readiness HTTP endpoints for all 5 services
- Reliability: Redis reconnect with exponential backoff in all services
- Reliability: DB partition automation with `pg_partman`
- Testing: Unit tests for D3, detector, classifier wrapper, ReID, auth routes, SHM buffer
- Testing: Integration test for camera connect → inference → alert flow
- Deployment: Remove pgadmin from production compose; add Nginx with TLS

---

### Phase 4 — Scale Readiness (2–3 months)

**Goal:** Support 10–50 cameras, multiple concurrent users, and horizontal inference scaling.

- Redis Sentinel or Cluster for HA
- Per-camera frame queues with consumer group per inference worker
- Replace base64 JPEG WS stream with MJPEG or HLS + server-sent events for detections overlay
- Replace MobileNetV3 ReID with Redis Search vector index (HNSW)
- Horizontal inference workers with proper GPU partitioning
- Kubernetes deployment manifests with GPU node selectors
- Model versioning: store model hash in DB with each incident for audit trail
- Evidence frame capture: write annotated JPEG to object storage (S3/MinIO) on confirmed incident
- Multi-tenant: per-customer camera namespacing and auth scopes

---

### Phase 5 — Product Maturity (3–6 months)

**Goal:** Enterprise-grade product with investor-grade quality signals.

- Role-based access control (security guard, store manager, regional manager)
- Multi-store dashboard with aggregate incident analytics
- False positive feedback loop: operators mark alerts as false positive; feed back to threshold tuning
- Model hot-reload without service restart
- Automated model performance dashboards (precision/recall per camera per week)
- SOC 2 / GDPR compliance layer: data retention policies, audit logs, PII handling for person crops
- SDK for camera integrators: document REST API + WebSocket protocol
- SLA monitoring: uptime tracking per camera, alert delivery SLA
- On-premise edge box packaging: single-node appliance with GPU, no cloud dependency

---

*End of audit. All findings sourced directly from codebase. No assumptions made about intended behavior beyond what the code and comments state.*




























