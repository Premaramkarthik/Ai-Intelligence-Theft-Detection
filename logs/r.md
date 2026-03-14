**“Do not just explain. Inspect the repo, implement the fixes in code, run verification, and report exactly what changed.”**

---

## IMPLEMENTATION PROMPT

You are a **principal software engineer, AI systems architect, backend lead, frontend lead, and production hardening engineer**.

I have an Edge AI software system with frontend + backend + inference + event pipeline.
A prior audit has already identified the main problems. Your task is to **implement the necessary fixes properly**, not just describe them.

You must behave like the owner of the codebase responsible for making the critical path work end to end.

Do **not** do a shallow cleanup.
Do **not** rewrite blindly.
Do **not** produce only suggestions.
You must inspect the repository, identify the exact files involved, implement the fixes in phases, and verify them.

---

# Context from audit

The audit found these critical issues:

### Critical problems

1. Event contracts are broken between inference, alerting, and persistence
2. Multi-camera inference state is shared globally and contaminates feeds
3. Frontend live stream path is broken and does not type-check
4. Frontend/backend WS protocol assumptions do not match
5. History page expects wrong payload fields
6. Sensitive/mutating endpoints and stream endpoints are unauthenticated
7. Hardcoded/default secrets and wildcard CORS are unsafe
8. Signaling startup/runtime dependency handling is weak
9. Queueing/backpressure behavior is unsafe
10. SHM lifecycle/versioning is unsafe

### Important problems

11. ReID logic is not scalable and may fail “successfully”
12. Docs/runtime/contracts are stale and drifted
13. Frontend state management is muddled
14. Config exists but is not fully consumed in inference
15. Tests do not protect the critical path

---

# Your implementation goals

You must make the system meaningfully more correct and production-safe by implementing the following in order.

## Phase 1 — Stabilize the critical path

Implement the smallest correct set of changes that makes the main product flow work:

* camera connect
* camera ingest
* inference output
* event emission
* alerting/persistence compatibility
* live frontend stream compatibility
* history API rendering compatibility

### Required changes in Phase 1

* define and use **one canonical event schema**
* separate **frame/stream telemetry messages** from **incident/action events**
* align inference output with alerting/persistence consumers
* align frontend WebSocket client and backend WS payload format
* fix history API/frontend field mismatch
* fix current frontend compile/type/runtime issues
* remove fake healthy UI states where backend truth is not available

## Phase 2 — Fix architecture correctness

Implement structural corrections where patching is not enough:

* isolate inference state per camera
* isolate temporal buffers per camera
* remove global mutable cross-camera state
* make config consumption explicit and real, or remove dead config knobs
* make camera connect idempotent or deduplicated

## Phase 3 — Security and runtime hardening

Implement immediate hardening:

* protect sensitive and streaming endpoints with real auth guards
* remove default secrets/admin credentials from code
* remove unsafe wildcard CORS behavior
* add startup/readiness checks for Redis/Postgres/model availability
* fail clearly when dependencies are unavailable instead of pretending the system is healthy

## Phase 4 — Reliability hardening

Implement safety improvements:

* replace unsafe queue drain/delete behavior
* add bounded queue or safer backpressure strategy
* add SHM generation/versioning or equivalent stale-reader protection
* improve reconnect/retry/degraded-state handling where essential

## Phase 5 — Verification

Add the minimum high-value tests:

* event schema contract tests
* frontend/backend API contract tests for critical endpoints
* WebSocket protocol compatibility tests
* multi-camera inference isolation tests
* auth protection tests

---

# Implementation rules

Follow these rules strictly:

1. **Inspect first, modify second**

   * read the existing repo carefully
   * identify exact files, modules, flows, and dependencies
   * do not assume the audit is perfectly complete; validate it in code

2. **Fix the root issue, not only symptoms**

   * if payload mismatch exists, unify the schema instead of adding fragile adapters everywhere
   * if inference state is global, redesign state ownership instead of patching around it

3. **Avoid unnecessary rewrites**

   * preserve working code where possible
   * redesign only where the audit explicitly shows patching is unsafe

4. **Keep contracts explicit**

   * use typed DTOs / schema models where appropriate
   * keep frontend/backend protocol definitions clear and centralized

5. **Preserve end-to-end operability**

   * do not break ingest while fixing UI
   * do not break persistence while fixing event shapes
   * do not create a new architecture that the rest of the repo cannot support

6. **Be brutally practical**

   * this is an implementation task, not a theory task
   * make the repo more correct and runnable

---

# Required output format

You must work in this exact order.

## Step 1 — Repository understanding

Before coding, explain briefly:

* current architecture as implemented
* critical path modules/files
* where the audit is correct
* where the audit needs refinement
* what you will change first and why

## Step 2 — Implementation plan

Create a phased implementation plan with:

* file-by-file targets
* what changes will be made
* dependencies/order of work
* risks of each change

## Step 3 — Apply changes

Implement the changes directly in the codebase.

For each phase:

* list files changed
* explain what was changed
* explain why
* keep changes coherent and production-minded

## Step 4 — Verification

Run and report:

* lint/typecheck where applicable
* relevant backend tests
* relevant frontend tests
* any new contract/integration tests you added
* what still fails, if anything
* whether failures are pre-existing or caused by your changes

## Step 5 — Final report

Provide:

* summary of what was fixed
* what remains risky
* what still requires deeper redesign later
* exact next steps for the next implementation pass

---

# Important engineering expectations

### On event schema

Create a canonical event model used across:

* inference producer
* alerting consumer
* persistence consumer
* API responses where appropriate

If needed, define:

* event_type
* camera_id
* trace_id
* timestamp
* frame reference or snapshot reference
* severity
* detections
* metadata/config version

Do not leave ambiguous field naming like one service using `created_at` while UI expects `timestamp`.

### On WebSocket / stream protocol

Create a clear backend-to-frontend message format and make both sides conform.

Do not keep ad hoc assumptions like:

* client expecting one shape
* server sending another
* mixed binary/json handling without protocol definition

If the current WS streaming approach is too broken, repair it in the simplest correct way without doing a giant transport rewrite unless absolutely necessary.

### On inference state

There must not be shared global mutable state across cameras for:

* previous detections
* temporal buffers
* frame counters
* track histories
* clip windows
* thresholds that should be camera-scoped

Move to per-camera state containers.

### On security

At minimum:

* protect mutating/config/streaming endpoints
* stop shipping dangerous defaults
* make env-based secrets mandatory or safer
* tighten CORS
* do not leave anonymous sensitive access in place

### On reliability

Do not leave unsafe behavior such as:

* deleting whole queues to recover lag
* stale SHM reads without version checks
* “healthy” UI with hardcoded optimistic labels

---

# Constraints

* Prefer focused, high-impact changes
* Do not do cosmetic cleanup unless it supports correctness
* Do not rewrite the whole platform
* Do not stop after analysis; actually implement
* If something is too large for one pass, complete the highest-value pass fully and report the boundary honestly

---

# Final instruction

Treat this as a **real stabilization sprint for a serious Edge AI product**.

Your mission is to make the system:

* more correct
* more coherent
* more secure
* more testable
* more operable

Start by reconstructing the current architecture from the repository, then execute the phased implementation.
