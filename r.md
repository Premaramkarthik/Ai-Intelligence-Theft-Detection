
# Implementation philosophy

We should not do one huge rewrite.

We should do this in **5 controlled phases**:

## Phase 1

Make the product **functionally correct**

## Phase 2

Make the product **architecturally clean and stable**

## Phase 3

Make the product **secure and production-safe**

## Phase 4

Make the product **reliable and test-protected**

## Phase 5

Make the product **scale-ready and product-mature**

---

# Master phase-wise implementation plan

---

# Phase 1 — Functional Correctness Stabilization

## Main goal

Fix the core pipeline so the product stops behaving falsely.

This is the most important phase.

Without this phase, nothing else matters.

---

## Problems to solve in this phase

### 1. D3 interaction detector is fake/mock

Right now it increments a counter for visible people instead of detecting real person-item interaction.

### 2. Tracker state is not properly isolated

`tracker_id` is discarded, so tracking identity can bleed across cameras.

### 3. Behavior classifier blocks async loop

GPU inference is happening in a way that freezes the inference loop.

### 4. ReID fallback is unsafe

Random embeddings create fake identity continuity.

### 5. Snapshot path is broken in Docker

Signaling reads SHM but Docker config does not support that path correctly.

### 6. DB partition expiry risk

Persistence will fail after defined partitions end.

---

## What to implement in Phase 1

### A. Replace mock interaction logic with real proximity logic

Implement a real first version of interaction detection using a practical heuristic.

### Recommended V1 heuristic

Since full hand-keypoint logic may be bigger, do this first:

* detect person bbox
* detect item bbox
* compute person lower-half centroid or lower-third zone
* compute distance / overlap with item bbox
* trigger interaction only if:

  * item is within threshold distance of person lower region
  * interaction persists for N frames
  * optional motion consistency check if available

This gives a usable V1 without waiting for a pose-estimation pipeline.

### Deliverable

`ItemInteractionDetector` must become a real spatial detector, not a frame counter.

---

### B. Fix per-camera tracking isolation

Do not discard `tracker_id`.

Need proper per-camera tracker separation.

### Deliverable

* each camera gets isolated tracking state
* no ID contamination across cameras
* tracking behavior becomes deterministic per stream

---

### C. Move classifier execution off the event loop

Wrap blocking GPU classification work in thread/offloaded execution.

### Deliverable

* inference loop continues processing frames
* classifier runs asynchronously without freezing the service
* latency becomes measurable and controllable

---

### D. Disable ReID when model is unavailable

No random embeddings.
If ReID model fails:

* log clearly
* mark ReID unavailable
* skip cross-camera identity linking

### Deliverable

system degrades honestly instead of failing silently

---

### E. Fix SHM access path for signaling

Choose one of these and commit properly:

#### Option 1 — Fastest fix

Add `ipc: host` for signaling in Docker

#### Option 2 — Better architecture

Stop signaling from reading SHM directly and instead serve snapshot bytes from MediaBridge or Redis-cached JPEG

For Phase 1, use **Option 1** if you need fast stabilization.
For later cleanup, move to Option 2.

---

### F. Extend DB partitions immediately

Add partitions for the near future right away.

Then in later phase automate partition creation.

---

## Files likely touched in Phase 1

Based on the report, probably:

* `backend/services/inference/services/interaction.py`
* `backend/services/inference/ml/engines/object_detector.py`
* `backend/services/inference/ml/engines/behavior_classifier.py`
* `backend/services/inference/pipeline.py`
* `backend/services/inference/services/reid_service.py`
* `backend/docker-compose.yml`
* `backend/scripts/schema.sql`

---

## Acceptance criteria for Phase 1

Phase 1 is complete only if all of these are true:

* a person standing in frame alone does **not** trigger interaction classification
* a person near item zone does trigger interaction candidate after threshold frames
* multi-camera streams do not share tracking IDs
* behavior classification no longer freezes the inference loop
* ReID failure disables ReID safely
* snapshot endpoint works in Docker
* incidents can persist beyond current month boundary

---

## Business outcome of Phase 1

After this phase, the product becomes:

* no longer obviously false
* demo-safe
* much closer to a real MVP

---

# Phase 2 — Critical Path Contract and Architecture Cleanup

## Main goal

Make all critical components speak the same language and reduce hidden coupling.

Phase 1 fixes correctness.
Phase 2 fixes structure.

---

## Problems to solve in this phase

### 1. Hidden coupling across services

Signaling importing from MediaBridge is a boundary violation.

### 2. Redis keyspace is scattered and undocumented

Key names are being used ad hoc.

### 3. Inference pipeline is a god object

Too many responsibilities are inside one class.

### 4. Duplicate DB session code exists

This creates maintenance risk.

### 5. Frontend types are duplicated locally

Schema changes can silently break UI.

### 6. Single shared `frames` queue

This will create fairness and starvation issues under multiple cameras.

---

## What to implement in Phase 2

### A. Create shared contracts/constants layer

Move all shared wire contracts and key namespaces into one central place.

### Include:

* event message models
* telemetry message models
* incident message models
* Redis key constants
* camera status keys
* stream names
* config key names

### Deliverable

all services use the same formal contracts

---

### B. Remove Signaling → MediaBridge direct import

Move `validate_source` into shared layer or create a validation utility that does not depend on MediaBridge internals.

### Deliverable

service boundaries become clean

---

### C. Split `InferencePipeline`

Break it into focused classes/modules such as:

* frame intake / queue consumer
* detection stage
* interaction stage
* classification stage
* telemetry publisher
* incident emitter
* config loader
* runtime state manager

### Deliverable

pipeline becomes testable and maintainable

---

### D. Merge duplicate DB session module

Keep one source of truth only.

---

### E. Introduce frontend shared types

Move stream payload types, incident types, and detection types into a shared frontend types layer.

---

### F. Replace single `frames` list with per-camera queues

Instead of one global queue:

* `frames:{camera_id}`

Later you can add scheduling/fairness logic if needed.

### Deliverable

one camera cannot starve another as easily

---

## Acceptance criteria for Phase 2

* no service imports another service’s internal runtime code
* Redis key names are centralized
* pipeline responsibilities are decomposed
* frontend payload types come from one place
* duplicate DB session code removed
* per-camera frame queues exist

---

## Business outcome of Phase 2

After this phase, the system becomes:

* cleaner to extend
* easier to test
* safer to change
* more correct under multiple cameras

---

# Phase 3 — Security and Production Safety Hardening

## Main goal

Stop unsafe defaults and close obvious attack/security weaknesses.

This phase is mandatory before any real pilot.

---

## Problems to solve in this phase

### 1. JWT in localStorage

XSS risk

### 2. WebSocket token in query params

Leaks into logs/history

### 3. Empty-string JWT secret in development

Dangerous

### 4. Metrics exposed without protection

Leaks internal state

### 5. PgAdmin exposed with bad defaults

Unsafe

### 6. RTSP credentials stored in plain form

Sensitive

### 7. Weak RTSP source validation

Possible SSRF/internal probing risk

---

## What to implement in Phase 3

### A. Move auth token to secure cookie model

Use:

* `httpOnly`
* `SameSite=Strict` or `Lax` depending on flow
* secure in non-local env

### Deliverable

no token in localStorage

---

### B. Change WebSocket auth method

Do not pass token in query string.

Use either:

* cookie auth
* first-message auth handshake
* subprotocol/header strategy if supported

For simplicity, cookie-based auth is usually easiest if same-origin.

---

### C. Make JWT secret mandatory in all environments

No empty default.
No silent fallback.

Add strong validation like:

* minimum length
* fail fast on startup

---

### D. Remove PgAdmin from main production compose

Move to a dev-only compose override.

---

### E. Protect `/metrics`

Expose internally only or place behind internal auth/network restrictions.

---

### F. Harden RTSP validation

Add SSRF-aware validation:

* restrict schemes
* reject localhost/internal reserved ranges if needed
* validate source shape more strictly

---

### G. Improve camera/config authorization model

Even if still single-admin, structure it properly:

* protected mutating endpoints
* protected stream endpoints
* protected config updates

---

## Acceptance criteria for Phase 3

* no JWT in localStorage
* no WS token in query params
* app fails startup if secret is invalid
* PgAdmin not exposed in production path
* metrics not public
* RTSP input validation is stronger
* sensitive endpoints are consistently protected

---

## Business outcome of Phase 3

After this phase, the system becomes:

* safer for real pilot
* less embarrassing in diligence review
* less dangerous on a shared/internal network

---

# Phase 4 — Reliability, Observability, and Testing

## Main goal

Make the system diagnosable, restart-safe, and regression-protected.

This phase makes it operationally trustworthy.

---

## Problems to solve in this phase

### 1. Very low test coverage

Core bugs slipped through because there were almost no tests.

### 2. Weak end-to-end traceability

Hard to trace an incident through the system.

### 3. No proper health/readiness across services

Only limited visibility

### 4. Redis and dependency restart behavior is weak

System can hang/crash together

### 5. No incident quality metrics

You cannot measure drift or false-positive behavior well

---

## What to implement in Phase 4

### A. Add core unit tests

Must cover:

* interaction detector logic
* tracker isolation
* ReID disabled behavior
* auth validation
* Redis key/contract handling

---

### B. Add integration tests

Must cover:

* camera connect flow
* frame pointer flow
* inference to incident emission
* alerting consumer path
* persistence write path
* `GET /api/events` response compatibility

---

### C. Add service health/readiness endpoints

For all services, expose at least:

* health
* readiness

Readiness should include dependency checks where appropriate.

---

### D. Improve trace IDs

Current short trace ID is too weak.

Use longer IDs and propagate them through:

* logs
* incident events
* DB writes
* Telegram alert metadata if appropriate

---

### E. Add better metrics

Include:

* incidents fired count
* classifier failures
* detector failures
* Redis reconnect count
* WS connection count
* queue depth
* per-camera lag
* frame drop reasons
* ReID disabled state
* interaction-trigger counts

---

### F. Add reconnect/backoff behavior

Services should reconnect gracefully to Redis and critical dependencies.

---

## Acceptance criteria for Phase 4

* core pipeline has unit tests
* main flow has integration tests
* all services expose health/readiness
* incident can be traced end-to-end
* system surfaces real metrics for debugging
* restart behavior is improved

---

## Business outcome of Phase 4

After this phase, the system becomes:

* operable
* debuggable
* safer to demo and pilot repeatedly
* much harder to accidentally break

---

# Phase 5 — Scale Readiness and Product Maturity

## Main goal

Prepare the platform for real multi-camera, multi-user, multi-store growth.

This phase is not “first priority,” but it is where the product becomes investor-grade.

---

## Problems to solve in this phase

### 1. Streaming path will not scale well

base64 JPEG over WS is heavy

### 2. Redis single node is a central failure point

No HA

### 3. ReID architecture still not truly scalable

HSCAN is only intermediate

### 4. No multi-tenant model

No store/customer separation

### 5. No evidence lifecycle and operator feedback loop

Product maturity is missing

---

## What to implement in Phase 5

### A. Replace current browser stream transport

Move from base64 JPEG-over-WS to something more suitable such as:

* MJPEG
* WebRTC
* HLS + event overlay channel
* MSE depending on latency needs

For edge retail real-time, WebRTC or MJPEG may be simpler depending on constraints.

---

### B. Improve Redis architecture

Move toward:

* Sentinel
* Cluster
* reconnect strategy
* fault-tolerant consumer behavior

---

### C. Use proper vector/indexed identity search

Replace Redis key scanning with:

* Redis Search vector indexing
* pgvector
* FAISS sidecar
* another explicit identity service

---

### D. Add multi-tenant data model

Need separation by:

* organization
* store
* camera
* user role

---

### E. Add evidence capture/storage lifecycle

On confirmed incident:

* save evidence frame/clip
* store metadata
* retention policy
* retrieval path
* audit trail

---

### F. Add operator feedback loop

Let human operator mark:

* true positive
* false positive
* uncertain

This is critical for improving thresholds and future model tuning.

---

### G. Add deployment maturity

* CI/CD
* environment promotion
* rollback
* migration safety
* config versioning
* model version tracking

---

## Acceptance criteria for Phase 5

* platform handles more cameras/users predictably
* evidence is captured and managed
* tenants/stores are isolated
* streaming architecture is more scalable
* product has operational maturity, not just technical capability

---

# Recommended execution order by weeks

Here is the practical order I would use.

## Sprint 1

Focus only on functional truth

* D3 real logic
* tracker isolation
* classifier async fix
* ReID safe-disable
* snapshot Docker fix
* DB partition extension

## Sprint 2

Critical structure cleanup

* shared contracts/constants
* remove cross-service import
* split inference pipeline
* duplicate DB cleanup
* per-camera frame queues
* shared frontend types

## Sprint 3

Security hardening

* cookie auth
* WS auth redesign
* metrics protection
* pgadmin cleanup
* secret validation
* RTSP validation hardening

## Sprint 4

Reliability and tests

* health/readiness endpoints
* unit tests
* integration tests
* trace propagation
* reconnect/backoff
* metrics expansion

## Sprint 5+

Scale/product maturity

* better streaming transport
* HA Redis
* vector-indexed ReID
* evidence lifecycle
* multi-tenant model
* operator feedback loop

---

# Priority matrix: what is absolutely first

## Must do before next serious demo

* D3 real logic
* tracker isolation
* classifier async fix
* ReID safe-disable
* snapshot fix
* DB partition fix

## Must do before any pilot

* secure auth/token handling
* metrics protection
* stronger RTSP validation
* tests for interaction/inference/auth
* health/readiness
* reconnect behavior

## Must do before real scale

* per-camera queues
* better stream transport
* Redis HA
* vector search for ReID
* multi-tenant model

---

# Clean end-state architecture after these phases

After the first 4 phases, your architecture should look like this:

## Control plane

* Signaling/API service
* auth
* camera/config management
* incident/history API

## Media plane

* MediaBridge
* SHM writer
* controlled frame publication

## Inference plane

* per-camera processing state
* detector
* interaction gate
* classifier
* telemetry + incident emitters

## Event plane

* Redis streams / queues with explicit contracts
* per-camera frame channels

## Alert plane

* Telegram/MQTT/other outbound alerting

## Persistence plane

* PostgreSQL with automated partitions
* evidence metadata
* incident auditability

## UI plane

* dashboard
* stream visualization
* history/review
* health-aware camera status
* reconnect-aware stream handling

---













