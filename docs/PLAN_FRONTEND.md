# Frontend Implementation Plan: Antigravity Vision

## 1. Project Initialization
- [ ] Initialize Next.js 15 project in `frontend/` using `npx create-next-app@latest`.
- [ ] Install dependencies: `zustand`, `lucide-react`, `@tanstack/react-query`, `framer-motion`.
- [ ] Configure Tailwind CSS v4 for dark mode and high-contrast accessibility.

## 2. Shared Infrastructure (Core)
- [ ] **State Management**: Implement `useCameraStore` (Zustand) for global stream tracking and health status.
- [ ] **API Layer**: Create a custom `apiClient` using TanStack Query for `status` and `connect` endpoints.
- [ ] **WebSocket Manager**: Develop a robust binary message parser for MJPEG streaming and JSON prediction updates.

## 3. UI Component Development (Bento Grid)
- [ ] **Dashboard Layout**: Implement a floating navigation sidebar and a responsive CSS grid for stream cards.
- [ ] **StreamCard**: Create a sophisticated video container with secondary `<canvas>` for AI overlays.
- [ ] **ConnectionPanel**: Build the RTSP/Webcam onboarding form with real-time feedback.
- [ ] **StatsOverlay**: Implement mini-charts/gauges for GPU VRAM, temperature, and FPS.

## 4. Integration & Refinement
- [ ] **MJPEG Sync**: Implement the frame buffer logic to synchronize bounding boxes with the video stream.
- [ ] **Health Checks**: Connect the `/api/status` endpoint to the UI heartbeat.
- [ ] **UX Polish**: Add Framer Motion transitions for card loading and detection highlights.

## 5. Verification
- [ ] Run `ux_audit.py` for accessibility and contrast compliance.
- [ ] Run `lint_runner.py` to ensure code quality.
- [ ] Execute Playwright E2E tests for the camera connection flow.

---
> **Target Directory**: `frontend/`
> **Primary Specialist**: @[frontend-specialist]
