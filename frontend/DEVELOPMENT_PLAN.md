# Frontend Development Plan: Antigravity Vision

> **Project:** Real-time AI Surveillance Dashboard  
> **Backend Integration:** Pipeline OpenCV (D1-D5 Staged Inference)  
> **Design Philosophy:** Sleek, High-Tech, Dark Mode

---

## 1. Technology Stack (2026 Standard)

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Framework** | **Next.js 15 (App Router)** | Performance, SEO (llms.txt), and robust API integration. |
| **Styling** | **Tailwind CSS v4** | Modern CSS-first configuration, high developer velocity. |
| **State** | **Zustand** | Lightweight, high-performance state management for multi-camera sync. |
| **Data Fetching** | **TanStack Query (v5)** | Intelligent caching, loading states, and auto-retries for camera APIs. |
| **Streaming** | **WebSocket (Binary)** | Low-latency MJPEG delivery already optimized in the backend. |
| **Overlays** | **HTML5 Canvas / SVG** | Precise bounding box rendering without DOM bloating. |
| **Icons** | **Lucide React** | Consistent, professional vector iconography. |

---

## 2. UI/UX Design System (The "Vision" Aesthetic)

Based on `ui-ux-pro-max` intelligence:
- **Palette**: `Deep Slate (#0F172A)` background with `Vibrant Blue (#3B82F6)` accents and `Neon Emerald (#10B981)` for healthy status indicators.
- **Typography**: `Fira Code` for data-heavy stats/IDs and `Fira Sans` for UI elements.
- **Layout**: **Bento Grid** for multi-camera monitoring. Large, cards-based interface with subtle glassmorphism (`backdrop-blur-md`).
- **Animations**: 200ms transitions for hover states; pulse animations for "LIVE" indicators.

---

## 3. Core Modules Implementation

### A. Camera Connection Gateway (Initial Screen)
A sophisticated multi-step form for hardware onboarding.
- **Form Fields**: Username, Password, IP, Port (554 default), Substream(s).
- **Backend Sync**: Hits `POST /api/camera/connect`.
- **Feedback**: Real-time validation, loading shimmer, and "Connection Successful" toast notifications.
- **Persistence**: Locally stores `camera_id` references for session recovery.

### B. Intelligent Stream Grid
The primary monitoring interface.
- **Streaming Strategy**: **MJPEG over WebSocket** (`ws://localhost:9000/ws/camera/{id}`).
- **Overlays**: A transparent `<canvas>` layer synced 1:1 with the video aspect ratio.
- **Detection Rendering**: Draws boxes/labels from `ws://localhost:9000/ws/predictions`. 
- **Sync Logic**: Use capture timestamps to match detection metadata with video frames (eliminates box-lag).

### C. Live Detection Analytics
A sidebar or bottom-panel feed for real-time events.
- **Event Feed**: Auto-scrolling list of detections (e.g., "Person Identified", "Interaction Detected").
- **Stat Cards**: Total person counts, active cameras, and system health (GPU VRAM/Temp).
- **Log Interaction**: Clicking a log item snapshots the related frame for review.

---

## 4. 🧠 Brainstorm: Communication Protocol

| Option | Pros | Cons | Recommendation |
| :--- | :--- | :--- | :--- |
| **WebSocket MJPEG** | Simple, fast, works everywhere. | High bandwidth. | **Primary (MVP)** |
| **WebRTC** | Ultra-low latency, efficient. | Complex NAT/ICE setup. | **Phase 2 Upgrade** |
| **HLS/DASH** | Massive scalability. | 5s+ Latency (Unusable). | **Discard** |

---

## 5. Technical Integration Details (Deep-Dive)

### A. State Management (Zustand)
We will use a centralized `useCameraStore` to manage globally consistent data:
-   **`cameras`**: Map of `camera_id` -> `metadata`.
-   **`activeStreams`**: Set of currently connected WebSocket instances.
-   **`globalStats`**: System health data from `/api/status`.
-   **`logFeed`**: A rolling buffer of the last 50 detection events.

### B. API Layer & Reconnection Logic
Using **TanStack Query** for persistent REST state:
- **`useConnectCamera`**: Mutation hook for `POST /api/camera/connect`.
- **WebSocket Hook**: Custom `useCameraStream(id)` that handles:
  - Binary parsing of MJPEG frames.
  - **Exponential Backoff**: Automatic reconnection if the stream drops (max 5 retries).
  - **Latency Check**: If frame lag > 2s, force a socket refresh.

### C. Synchronization Strategy (Metadata + Video)
To prevent "box jitter" (where boxes appear before or after the person):
1.  **Frame Buffer**: Maintain a micro-buffer (3-5 frames) of incoming binary data.
2.  **Metadata Alignment**: Each `Detection` event from the backend includes a `ts` (capture timestamp).
3.  **Draw Loop**: The `<canvas>` renderer draws the `Detection` only when the video buffer reaches the matching frame timestamp.

---

## 6. Suggested Backend Improvements (Frontend-Aware)

| Improvement | Rationale |
| :--- | :--- |
| **GET /api/status** | **Already Implemented**. Provides telemetry. |
| **DELETE /api/camera/{id}** | **Planned**. Ensures resources are released when the user closes a preview. |
| **Snapshot API** | **Planned**. Allows the frontend to show a static image in the dashboard list view before the user starts the live feed (saves GPU). |
| **Auth JWT** | **Review Stage**. Required for public-facing deployments. |

---

## 7. Architecture Integration Roadmap

1.  **Phase 1 (Scaffolding)**: Next.js setup + `Status API` dashboard (Read-only).
2.  **Phase 2 (Control Logic)**: Camera Connection Form + `POST /connect` implementation.
3.  **Phase 3 (Binary Streaming)**: WebSocket integration + Canvas overlay rendering.
4.  **Phase 4 (Polish & Flow)**: Bento Grid responsiveness + Framer Motion animations.

---

> **Plan Location:** `frontend/DEVELOPMENT_PLAN.md`  
> **Status:** Finalized for implementation.
