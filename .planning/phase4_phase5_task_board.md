# Phase 4-5 Task Board

This board converts the Phase 4 and Phase 5 roadmap into implementation tasks mapped to the current repository layout.

## Assumed owner roles

- `BE-Inference`: `backend/services/inference`, `backend/shared/redis`, inference tests/docs
- `BE-Signaling`: `backend/services/signaling`, contracts, signaling tests/docs
- `BE-Persistence`: `backend/services/persistence`, schema, DB writers/models
- `FE-App`: `frontend/src`
- `Platform`: docker, CI, env validation, runtime docs, deployment/runbooks

## Status legend

- `existing`: already partially present in codebase, requires hardening/completion
- `new`: not materially implemented yet

## Sprint 4.1 Queue Fairness

| Task ID | Scope | Status | Owner | Files / Modules | Dependencies | Acceptance criteria | Effort |
|---|---|---|---|---|---|---|---|
| P4-1.1 | Remove legacy global queue path and make per-camera queues the only active ingest contract | existing | BE-Inference | `backend/shared/redis/frame_queue.py`, `backend/shared/redis/keys.py`, `backend/shared/core/settings.py`, `backend/docs/services/inference.md`, `backend/tests/test_reliability_hardening.py` | none | `legacy_global_frame_queue` removed or defaults inactive everywhere, all enqueue/dequeue paths use `frames:{camera_id}`, tests cover no-write/no-read on global queue | M |
| P4-1.2 | Make fair round-robin scheduling explicit and deterministic across active cameras | existing | BE-Inference | `backend/services/inference/main.py`, `backend/shared/redis/frame_queue.py`, `backend/tests/test_inference_isolation.py`, `backend/tests/integration/test_video_pipeline.py` | P4-1.1 | scheduler keeps stable rotation cursor, idle cameras do not starve active peers, fairness test demonstrates busy camera cannot monopolize processing | M |
| P4-1.3 | Define stale frame policy for age, generation mismatch, and queue overflow | existing | BE-Inference | `backend/shared/redis/frame_queue.py`, `backend/services/inference/frame_input.py`, `backend/services/inference/main.py`, `backend/shared/types/models.py`, `backend/shared/core/settings.py` | P4-1.1 | documented and enforced policy for age drops, generation mismatch drops, overflow drops, behavior is deterministic and metric-backed | M |
| P4-1.4 | Add per-camera queue observability | existing | BE-Inference | `backend/services/inference/utils/metrics.py`, `backend/services/mediabridge/utils/metrics.py`, `backend/services/inference/main.py`, `backend/services/mediabridge/main.py` | P4-1.2, P4-1.3 | metrics expose queue depth, stale drops, oldest frame age, processing lag by camera and are visible on runtime endpoints | S |
| P4-1.5 | Add queue pressure and fairness regression tests | new | BE-Inference | `backend/tests/test_reliability_hardening.py`, `backend/tests/test_inference_isolation.py`, `backend/tests/integration/test_e2e_latency.py` | P4-1.2, P4-1.3, P4-1.4 | tests simulate one hot camera plus multiple normal cameras and assert bounded lag and non-zero throughput for all active cameras | M |

## Sprint 4.2 Stream Delivery

| Task ID | Scope | Status | Owner | Files / Modules | Dependencies | Acceptance criteria | Effort |
|---|---|---|---|---|---|---|---|
| P4-2.1 | Standardize MJPEG preview as the only browser image transport | existing | BE-Signaling | `backend/services/signaling/api/routes/camera.py`, `backend/services/signaling/ws/camera_stream.py`, `backend/docs/services/signaling.md`, `backend/tests/test_signaling_contracts.py` | none | browser preview path uses HTTP MJPEG endpoint only, websocket frame-image payload path removed from active contract | M |
| P4-2.2 | Keep `/ws/camera/{camera_id}` metadata-only and contract-test it | existing | BE-Signaling | `backend/services/signaling/ws/camera_stream.py`, `backend/shared/types/events.py`, `frontend/src/types/contracts.ts`, `backend/tests/test_signaling_contracts.py` | P4-2.1 | websocket contract emits detections/incidents/stream state only, no base64 image payload fields remain | S |
| P4-2.3 | Complete frontend preview refactor around MJPEG plus overlay canvas | existing | FE-App | `frontend/src/components/dashboard/StreamCard.tsx`, `frontend/src/types/contracts.ts`, `frontend/src/app/page.tsx` | P4-2.2 | live preview renders via `<img>` MJPEG, overlays stay aligned, reconnect/offline states behave correctly | S |
| P4-2.4 | Add preview client and failure metrics | new | BE-Signaling | `backend/services/signaling/utils/metrics.py`, `backend/services/signaling/ws/camera_stream.py`, `backend/services/signaling/api/routes/camera.py` | P4-2.1, P4-2.2 | metrics expose active preview clients, MJPEG snapshot failures, stream disconnects, auth failures | S |
| P4-2.5 | Validate bandwidth/browser overhead reduction and document rollout | new | Platform | `backend/docs/services/signaling.md`, `backend/docs/backend_architecture.md`, `.planning/` notes if needed | P4-2.1 through P4-2.4 | doc captures before/after message path and expected bandwidth reduction, no base64 frames on WS path in packet inspection/test logs | S |

## Sprint 4.3 Evidence Capture

| Task ID | Scope | Status | Owner | Files / Modules | Dependencies | Acceptance criteria | Effort |
|---|---|---|---|---|---|---|---|
| P4-3.1 | Save annotated evidence JPEG on confirmed incident | existing | BE-Inference | `backend/services/inference/evidence.py`, `backend/services/inference/ml/pipeline.py`, `backend/services/inference/publishers.py`, `backend/shared/core/settings.py` | none | confirmed incidents persist evidence and thumbnail URIs, output image contains overlays or incident annotation | M |
| P4-3.2 | Persist evidence metadata through event writer and schema | existing | BE-Persistence | `backend/scripts/schema.sql`, `backend/services/persistence/services/writer.py`, `backend/services/persistence/models/events.py`, `backend/shared/types/events.py` | P4-3.1 | `trace_id`, `camera_id`, `model_version`, `config_version`, `evidence_uri`, `thumbnail_uri` persist and survive API reads | M |
| P4-3.3 | Expose evidence in history/event APIs | existing | BE-Signaling | `backend/services/signaling/api/routes/events.py`, `backend/services/signaling/schemas`, `backend/tests/test_contracts.py` | P4-3.2 | history/detail payloads include evidence fields with stable contract | S |
| P4-3.4 | Render evidence thumbnails in history UI | existing | FE-App | `frontend/src/app/history/page.tsx`, `frontend/src/types/view-models.ts`, `frontend/src/types/contracts.ts` | P4-3.3 | history page shows thumbnail and drill-down evidence link without breaking current event list | S |
| P4-3.5 | Add durable evidence volume and optional clip-capture design note | new | Platform | `backend/docker-compose.yml`, `backend/docs/services/persistence.md`, `backend/docs/phase5_runbook.md` | P4-3.1 | evidence path mounted durably, retention expectation documented, clip capture explicitly deferred or implemented behind flag | S |

## Sprint 4.4 ReID and Multi-Tenant Foundation

| Task ID | Scope | Status | Owner | Files / Modules | Dependencies | Acceptance criteria | Effort |
|---|---|---|---|---|---|---|---|
| P4-4.1 | Make ReID explicitly opt-in with backend feature flags and health metrics | existing | BE-Inference | `backend/services/inference/services/reid_service.py`, `backend/shared/core/settings.py`, `backend/services/inference/utils/metrics.py`, `backend/docs/services/inference.md` | none | `REID_ENABLED` and `REID_BACKEND` fully gate behavior, disabled state is explicit, availability and failures are observable | S |
| P4-4.2 | Remove any remaining scan-based or implicit legacy identity path from production code | new | BE-Inference | `backend/services/inference/services/reid_service.py`, `backend/services/inference/services/interaction.py`, repo-wide search in inference modules/tests | P4-4.1 | no key-scan lookup remains in active inference path, docs reflect pgvector-only scale path | S |
| P4-4.3 | Harden pgvector schema and DB bootstrap for identity lookup | existing | BE-Persistence | `backend/scripts/schema.sql`, `backend/services/persistence/main.py`, `backend/README.md` | P4-4.1 | pgvector extension handling is documented, `reid_identities` bootstrap is deterministic, migration/check path reports missing extension cleanly | M |
| P4-4.4 | Introduce store-aware domain foundation across cameras and incidents | existing | BE-Persistence | `backend/scripts/schema.sql`, `backend/services/signaling/api/routes/cameras.py`, `backend/services/signaling/api/routes/events.py`, `backend/services/signaling/services/camera_service.py`, `backend/shared/core/settings.py` | none | APIs read/write `organization_id` and `store_id`, defaults are no longer silently assumed in core flows | L |
| P4-4.5 | Add store-scoped frontend filtering for cameras and incidents | new | FE-App | `frontend/src/app/cameras/page.tsx`, `frontend/src/app/history/page.tsx`, `frontend/src/stores/useCameraStore.ts`, `frontend/src/types/view-models.ts` | P4-4.4 | operator can filter by store in camera/history views, requests pass store scope to backend | M |

## Sprint 4.5 Worker Readiness and Deployment Maturity

| Task ID | Scope | Status | Owner | Files / Modules | Dependencies | Acceptance criteria | Effort |
|---|---|---|---|---|---|---|---|
| P4-5.1 | Define worker-safe camera ownership model for multi-worker inference | existing | BE-Inference | `backend/services/inference/main.py`, `backend/services/inference/runtime.py`, `backend/services/inference/ml/model_manager.py`, `backend/tests/test_inference_isolation.py` | P4-1.2 | camera-to-worker assignment strategy is explicit, worker ownership does not overlap unless configured, docs state single-GPU assumptions | L |
| P4-5.2 | Add worker count, max cameras per worker, and assignment mode config | new | BE-Inference | `backend/shared/core/settings.py`, `backend/services/inference/main.py`, `backend/docs/services/inference.md` | P4-5.1 | config supports worker count, max cameras per worker, assignment mode; defaults preserve current runtime behavior | M |
| P4-5.3 | Add multi-worker isolation tests | new | BE-Inference | `backend/tests/test_inference_isolation.py`, `backend/tests/integration/test_video_pipeline.py` | P4-5.1, P4-5.2 | tests prove no cross-camera contamination and stable ownership under multiple workers | M |
| P4-5.4 | Prepare Redis settings/connection abstraction for future HA modes | new | Platform | `backend/shared/core/settings.py`, `backend/shared/core/config.py`, `backend/shared/redis/__init__.py`, service startup modules | none | settings support single-node now plus sentinel-ready structure later, current path remains unchanged | M |
| P4-5.5 | Add CI lint/test/build workflow, env validation, migration check, and deployment runbook updates | new | Platform | `.github/workflows/*`, `backend/pyproject.toml`, `frontend/package.json`, `backend/docs/local_setup.md`, `backend/docs/phase5_runbook.md`, `backend/README.md` | P4-5.2, P4-4.3 | CI runs backend tests plus frontend lint/build, env validation fails fast, migration/schema check is part of deploy workflow | L |

## Phase 5.1 RBAC

| Task ID | Scope | Status | Owner | Files / Modules | Dependencies | Acceptance criteria | Effort |
|---|---|---|---|---|---|---|---|
| P5-1.1 | Add role model and scoped claims | new | BE-Signaling | `backend/services/signaling/api/routes/auth.py`, `backend/services/signaling/schemas/auth.py`, `backend/shared/core/settings.py`, DB schema additions | P4-4.4 | auth token/session includes role plus store/org scope, roles support operator, store manager, regional manager, org admin | L |
| P5-1.2 | Enforce authorization middleware/helpers for camera, incident, config, evidence actions | new | BE-Signaling | `backend/services/signaling/api/deps.py`, `backend/services/signaling/core/security.py`, routes under `backend/services/signaling/api/routes` | P5-1.1 | forbidden actions are blocked by role and scope across protected routes | L |
| P5-1.3 | Add role-aware UI visibility | new | FE-App | `frontend/src/stores/useAuthStore.ts`, `frontend/src/components/layout/Sidebar.tsx`, app pages/components | P5-1.1, P5-1.2 | UI hides or disables actions not permitted for current role without relying solely on frontend enforcement | M |

## Phase 5.2-5.5 Product Workflows and Analytics

| Task ID | Scope | Status | Owner | Files / Modules | Dependencies | Acceptance criteria | Effort |
|---|---|---|---|---|---|---|---|
| P5-2.1 | Build multi-store aggregate dashboard APIs | new | BE-Persistence | `backend/services/signaling/api/routes/events.py`, aggregation query layer in persistence/signaling, schema support | P4-4.4 | APIs support aggregation by store, camera, time range, status | L |
| P5-2.2 | Build manager dashboard UI with filters and summary cards | new | FE-App | `frontend/src/app/page.tsx`, dashboard components under `frontend/src/components/dashboard` | P5-2.1 | managers can filter by store/date/camera/status and view totals, confirmed, false positives, pending review, active cameras | L |
| P5-3.1 | Add review workflow fields and review APIs | existing | BE-Persistence | `backend/scripts/schema.sql`, `backend/services/signaling/api/routes/events.py`, `backend/services/persistence/models/events.py` | P4-3.2 | events can be marked confirmed, false positive, needs review with note and reviewer identity if available | M |
| P5-3.2 | Add history/detail review controls and feedback export path | new | FE-App / BE-Persistence | `frontend/src/app/history/page.tsx`, `backend/services/signaling/api/routes/events.py`, export job or endpoint | P5-3.1 | operators can review incidents and export feedback data for downstream tuning | M |
| P5-4.1 | Propagate detector/classifier/config version metadata through incidents and evidence | existing | BE-Inference | `backend/services/inference/ml/model_manager.py`, `backend/services/inference/ml/pipeline.py`, `backend/shared/core/settings.py`, persistence writer path | P4-3.2 | incidents expose detector, classifier, config versions consistently in APIs/UI | M |
| P5-4.2 | Add controlled model reload workflow | new | BE-Inference | `backend/services/inference/runtime.py`, `backend/services/inference/ml/model_manager.py`, admin API/docs | P5-4.1, P5-1.2 | operator/admin can trigger controlled reload or documented safe reload workflow without full blind restart | L |
| P5-5.1 | Build performance analytics APIs for weekly trends and version comparisons | new | BE-Persistence | aggregation endpoints, scheduled jobs if needed | P5-2.1, P5-3.1, P5-4.1 | APIs provide incident counts, confirmed rate, false-positive rate, review latency, version comparison | L |
| P5-5.2 | Build analytics dashboard views | new | FE-App | dashboard/history analytics pages and chart components | P5-5.1 | charts surface per-camera/per-store trends and review throughput | L |

## Phase 5.6-5.9 Trust, Integration, Packaging

| Task ID | Scope | Status | Owner | Files / Modules | Dependencies | Acceptance criteria | Effort |
|---|---|---|---|---|---|---|---|
| P5-6.1 | Add audit trail model and write hooks for critical actions | new | BE-Persistence | schema, auth/config/camera/review/evidence access paths | P5-1.2, P5-3.1 | login/logout, config changes, camera changes, reviews, evidence access are auditable | L |
| P5-6.2 | Add retention and evidence governance configuration/docs | new | Platform | `backend/shared/core/settings.py`, docs, evidence handling paths | P4-3.5, P5-6.1 | retention policy and PII handling are configurable and documented | M |
| P5-7.1 | Publish REST and protocol docs with stable payload contracts | existing | Platform / BE-Signaling | `backend/docs/api.md`, `backend/docs/services/signaling.md`, `frontend/src/types/contracts.ts` | P4-2.2, P5-1.2 | docs describe supported endpoints, camera metadata/event protocol, evidence retrieval, review workflow | M |
| P5-7.2 | Add integration examples for cameras, incidents, reviews, evidence | new | Platform | docs/examples location to be created, potentially `backend/docs` | P5-7.1 | external integrator can complete core flows without reverse engineering frontend or backend code | M |
| P5-8.1 | Add uptime and SLA metrics for cameras and incident delivery | new | BE-Signaling / BE-Inference | runtime metrics modules, camera/status websocket and persistence aggregation | P4-1.4, P5-2.1 | camera online/offline history, incident delivery success, review latency, and uptime summaries are measurable | L |
| P5-8.2 | Surface availability dashboards | new | FE-App | dashboard pages/components | P5-8.1 | operators and managers can inspect historical reliability and SLA-style summaries | M |
| P5-9.1 | Create on-prem edge deployment profile and appliance runbook | new | Platform | `backend/docker-compose.yml`, `backend/docs/local_setup.md`, `backend/docs/phase5_runbook.md`, root start/stop scripts | P4-5.5 | single-node edge profile, hardware/software prerequisites, install/update/rollback guide are documented and runnable | L |

## Recommended execution order

1. Finish Phase 4 items that are already partly implemented: P4-1.1 through P4-1.4, P4-2.1 through P4-2.3, P4-3.1 through P4-3.4, P4-4.1, P4-4.3, P4-4.4.
2. Then close scale-risk gaps: P4-1.5, P4-2.4, P4-5.1 through P4-5.5.
3. Start product controls only after store scoping is real: P5-1.*, P5-3.1.
4. Build dashboards and analytics after review data and role scoping exist: P5-2.*, P5-5.*.
5. Finish trust/packaging work last: P5-6.*, P5-7.*, P5-8.*, P5-9.1.

## Critical path notes

- The codebase already contains partial implementations for per-camera queueing, fair dequeue, MJPEG preview, evidence save helpers, review fields, store IDs, and pgvector-backed ReID.
- The highest-value Phase 4 work is not greenfield. It is contract cleanup, observability, test hardening, and explicit configuration/ownership semantics.
- `backend/services/inference/main.py` already supports multiple workers at a coarse level, but it does not yet amount to a documented, worker-safe assignment model.
- `frontend/src/components/dashboard/StreamCard.tsx` is already aligned with the intended MJPEG plus metadata architecture, so the remaining work is contract enforcement and metrics rather than a UI rewrite.

## Suggested first three implementation tickets

1. `P4-1.1` plus `P4-1.3`: finalize queue contract and stale-drop rules.
2. `P4-2.2` plus `P4-2.4`: lock metadata-only websocket contract and add preview metrics.
3. `P4-5.1` plus `P4-5.2`: define worker ownership semantics before scaling worker count further.
