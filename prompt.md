**“First read the full repository completely. Do not answer until you understand the architecture and end-to-end flow.”**
---

## Your Objective

Audit this project across:

1. **Business purpose and product flow**
2. **System architecture**
3. **Frontend architecture and UX logic**
4. **Backend architecture and API design**
5. **AI/ML / Edge inference pipeline**
6. **Data flow and state flow**
7. **Code quality and maintainability**
8. **Scalability and performance**
9. **Security and privacy**
10. **Observability, logging, and debugging**
11. **Deployment readiness**
12. **Failure modes and risk areas**
13. **Refactor recommendations**
14. **Production-grade roadmap**

You must behave like the software is intended to become a **real production-grade product**, not a student demo.

---

## Core Instructions

First, understand the project fully before judging it.

You must:

* inspect the entire repo structure
* understand each module’s role
* trace the end-to-end request and response lifecycle
* identify how data moves through the system
* identify how the user interacts with the system
* identify how frontend, backend, services, AI components, storage, queues, workers, and external integrations connect together
* identify assumptions, hidden coupling, design shortcuts, and technical debt
* identify what is production-grade and what is still prototype-grade

Do not assume the current implementation is correct.
Challenge everything.

Think like:

* CTO
* senior architect
* senior SRE
* AI systems engineer
* security reviewer
* product engineering lead

---

# Deliverables Required

Give the output in the following structure.

---

## 1. Executive Summary

Explain:

* what this software appears to do
* what business problem it solves
* whether the architecture matches the product goal
* whether it currently looks like:

  * prototype
  * MVP
  * internal tool
  * early production
  * scale-ready system

Then give a **final high-level verdict**:

* strongest parts
* weakest parts
* top technical risks
* top opportunities

---

## 2. Product Understanding

Infer and explain clearly:

* what the software is meant to do
* who the user is
* what the core workflow is
* what the expected end-to-end lifecycle is
* what the important user actions are
* what the critical product outcomes are

Then tell me whether the code actually supports that product vision properly.

---

## 3. Repo Structure Audit

Analyze the full repository structure.

For each major folder/file:

* explain its role
* explain whether the placement is logical
* identify duplication or poor organization
* identify missing layers or mixed concerns
* identify whether naming conventions are clean and scalable

Then give:

* current repo maturity score out of 10
* ideal repo restructuring plan

---

## 4. Architecture Audit

Reverse-engineer the architecture and explain:

* system components
* boundaries between components
* frontend/backend interaction
* service-to-service interaction
* AI inference flow
* event flow
* storage flow
* async/background processing flow
* external integrations
* configuration flow

Then answer:

* Is the architecture clean?
* Is it modular?
* Is it tightly coupled?
* Where are the bottlenecks?
* What breaks first under scale?
* What is missing for real-world deployment?

Also provide:

* current architecture pattern used
* whether it is monolith / modular monolith / microservice-ish / hybrid
* whether that choice is appropriate

---

## 5. Frontend Audit

Review the frontend deeply.

Analyze:

* page structure
* component structure
* routing
* state management
* API integration
* error handling
* loading states
* user feedback
* responsiveness
* maintainability
* coupling with backend assumptions

Check for:

* bad component boundaries
* prop drilling / state chaos
* fragile UI logic
* hardcoded values
* poor UX around failure states
* poor form validation
* missing retry behavior
* missing optimistic/pessimistic flow handling
* inconsistent API handling
* security issues in UI

Then give:

* frontend architecture score
* frontend UX maturity score
* frontend maintainability score
* exact refactor suggestions

---

## 6. Backend Audit

Review the backend deeply.

Analyze:

* API structure
* route design
* controller/service/repository separation
* business logic placement
* validation
* error handling
* middleware
* auth/authz if present
* job orchestration
* background tasks
* concurrency handling
* database access
* retries
* timeouts
* idempotency
* config management
* secrets handling

Check whether backend logic is:

* clean
* testable
* scalable
* observable
* secure
* production-safe

Identify:

* hidden coupling
* brittle flows
* overgrown service logic
* poor abstractions
* anti-patterns
* duplicated logic
* incomplete failure handling

Then give:

* backend architecture score
* API design score
* production-readiness score
* concrete fixes

---

## 7. End-to-End Data Flow Audit

Trace the full flow from:

**user action → frontend → API → backend services → model/inference/pipeline → storage → response → frontend display**

Explain exactly:

* what enters the system
* how it is transformed
* where it is stored
* where state is updated
* where failures can happen
* where latency is introduced
* where race conditions or stale data can happen
* where silent failures may exist

Create a step-by-step flow map.

Then tell me:

* whether the flow is robust
* whether it is easy to debug
* whether it is safe under retries or restarts
* whether the flow is deterministic enough

---

## 8. AI / Edge / Model Pipeline Audit

Because this is Edge AI software, inspect the AI pipeline deeply.

Analyze:

* model loading
* inference lifecycle
* preprocessing
* postprocessing
* detection/tracking/classification/eventing logic
* batching or frame handling
* queueing and buffering
* device constraints
* hardware assumptions
* GPU/CPU usage assumptions
* real-time guarantees
* fallback behavior
* latency risks
* memory risks
* failure handling if model crashes
* hot reload / model swap behavior if any
* threshold handling
* calibration logic
* false positive / false negative risks
* observability of inference outputs

Check:

* whether the AI logic is mixed incorrectly with app logic
* whether business logic depends too tightly on raw detections
* whether the system can be tuned safely
* whether the system is edge-deployable in the real world
* whether restarts and recovery are handled properly

Then give:

* ML pipeline score
* edge deployment score
* inference reliability score
* top 10 technical weaknesses in the AI layer

---

## 9. Performance and Scalability Audit

Audit the system for performance and future scale.

Inspect:

* request latency
* inference latency
* UI responsiveness
* database bottlenecks
* blocking code
* async correctness
* queueing issues
* memory growth
* CPU/GPU contention
* repeated unnecessary computation
* N+1 patterns
* redundant serialization/deserialization
* frontend over-fetching
* backend bottlenecks
* startup time
* shutdown behavior

Then answer:

* what happens with 10 users?
* what happens with 100 users?
* what happens with 1000 devices or streams?
* what happens with long-running execution?
* what happens under network instability?

Then recommend:

* immediate performance fixes
* medium-term scale changes
* long-term architecture upgrades

---

## 10. Reliability and Failure Mode Audit

Identify every important failure path.

Think in terms of:

* app crash
* backend restart
* model crash
* dropped frames
* API timeout
* DB unavailable
* Redis/queue unavailable
* frontend refresh mid-process
* duplicate request
* partial write
* corrupted config
* bad environment variable
* missing hardware dependency
* invalid input
* race conditions
* inconsistent state
* worker death
* container restart

For each:

* describe what likely happens today
* describe the risk
* describe what should happen in production instead

Then give a **failure mode table** with:

* failure
* current behavior
* risk level
* recommended safeguard

---

## 11. Security Audit

Review for real-world security risks.

Analyze:

* auth and authz
* token handling
* session handling
* secrets management
* CORS
* input validation
* output sanitization
* SSRF risk
* command execution risk
* file upload safety
* path traversal
* insecure defaults
* environment leaks
* logs leaking secrets
* model endpoint exposure
* admin/debug routes exposed
* local device security assumptions
* data retention/privacy issues

Then classify findings by severity:

* critical
* high
* medium
* low

Be strict.

---

## 12. Observability and Debuggability Audit

Check whether this system is actually operable in production.

Analyze:

* logging quality
* structured logs
* traceability across request lifecycle
* correlation IDs
* metrics
* health checks
* readiness checks
* liveness checks
* alerting points
* dashboards readiness
* debug friendliness
* reproducibility

Then answer:

* if a bug happens in production, how hard is it to diagnose?
* if inference quality drops, would we know?
* if the frontend breaks due to backend change, would it be obvious?
* if latency rises slowly over time, would the system reveal it?

Then recommend:

* exact observability additions needed

---

## 13. Code Quality Audit

Review code quality deeply.

Check for:

* readability
* modularity
* dead code
* duplication
* weak naming
* giant files
* giant functions
* God objects
* bad abstractions
* inconsistent patterns
* weak typing
* fragile imports
* hidden side effects
* hardcoded constants
* poor comments
* misleading comments
* lack of contracts/interfaces
* poor config separation
* testability issues

Then provide:

* code quality score
* maintainability score
* refactor priority list

---

## 14. Testing Audit

Analyze testing quality.

Check:

* unit tests
* integration tests
* end-to-end tests
* API tests
* UI tests
* inference pipeline tests
* regression tests
* load tests
* failure tests
* mocks/stubs
* test organization
* CI test readiness

Then answer:

* what is dangerously untested?
* what should be tested first?
* what bugs are likely slipping through because of lack of testing?

Then provide a **testing roadmap**:

* must add immediately
* should add next
* optional but valuable

---

## 15. Deployment / DevOps / Production Readiness Audit

Analyze whether this can be deployed and maintained like a real product.

Check:

* Docker quality
* docker-compose quality
* env management
* build reproducibility
* dependency pinning
* CI/CD readiness
* release safety
* secrets handling
* runtime portability
* hardware-specific assumptions
* cloud readiness
* edge-device readiness
* rollback readiness
* versioning
* migration safety
* startup/shutdown sequencing

Then answer:

* can this be reliably deployed today?
* what environment would it break in?
* what manual steps make it fragile?
* what is needed for zero-downtime or safe updates?

---

## 16. Architecture Smells and Technical Debt

List the biggest architecture smells.

For each one:

* explain the smell
* explain the business risk
* explain the technical risk
* explain the future scale risk
* recommend the fix

Prioritize by:

* urgent
* important
* later

---

## 17. Brutal Truth Section

Be brutally honest.

Tell me:

* what parts look impressive
* what parts are pretending to be scalable but are not
* what parts are likely to fail in production
* what parts need redesign instead of patching
* what gives confidence
* what would scare an investor, CTO, or enterprise buyer

---

## 18. Scoring Dashboard

Give scores out of 10 for:

* product clarity
* repo structure
* frontend design
* backend design
* API quality
* AI pipeline design
* scalability
* reliability
* security
* observability
* code quality
* testing
* deployment readiness
* production readiness overall

Then give one final rating:

* hobby prototype
* serious prototype
* strong MVP
* near-production
* production-capable
* enterprise-capable

---

## 19. Top 20 Fixes

Give the top 20 improvements in priority order.

For each:

* issue
* why it matters
* impact
* difficulty
* recommended action

Group into:

* immediate
* short-term
* medium-term

---

## 20. Refactor Roadmap

Create a phased plan:

### Phase 1 — Stabilize

What must be fixed first to reduce risk

### Phase 2 — Clean Architecture

What should be refactored for clarity and maintainability

### Phase 3 — Production Hardening

What should be added for reliability, security, observability, testing

### Phase 4 — Scale Readiness

What changes are needed for multi-device, multi-customer, or enterprise scale

### Phase 5 — Product Maturity

What is needed to make it investor-grade / enterprise-grade / 10M-worth product quality

---

# How to Review the Code

While auditing, do all of the following:

* inspect every important code path
* trace the actual execution path
* identify where functions are called from
* inspect configs, env files, Docker files, scripts, tests, schemas, models, services, routes, hooks, pages, components, workers, and utilities
* detect architecture by reading code, not by guessing
* identify mismatch between intended design and actual implementation
* call out dead features, half-built flows, misleading abstractions, and hidden hacks
* separate “works locally” from “production ready”

---

# Output Style Rules

Your response must be:

* very structured
* direct
* brutally honest
* technically deep
* concrete
* no fluff
* no generic advice
* no vague “could be improved”
* every criticism must explain why it matters
* every recommendation must be actionable

When possible, cite:

* exact files
* exact modules
* exact flows
* exact bad patterns
* exact architectural risks

If something is missing, say so clearly.

If something is strong, say why.

If something is dangerous, say how it can fail in the real world.

---

# Final Instruction

Do not behave like a tutor.
Behave like a **real audit team delivering an engineering diligence report**.

I want the truth, not politeness.

Start by first reconstructing the system from the codebase, then perform the audit section by section.

---
