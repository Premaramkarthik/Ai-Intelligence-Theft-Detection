# AI Surveillance Frontend - Design System

This document outlines the usage of the modular, minimalist, and high-performance design system established in `app/components/design-system`.

## 1. Foundation & Tokens

The application uses standard Tailwind CSS v4 configured inside `app/globals.css`. 
It utilizes a strict variable palette (e.g., `--bg-primary`, `--bg-secondary`, `--accent-active`) rather than hardcoded grays to ensure absolute consistency. 

All interactive components utilize the custom `cn` utility located in `utils/cn.ts` which safely resolves conflicting Tailwind classes using `tailwind-merge` and `clsx`.

## 2. Core Components

### `Button`
```tsx
import { Button } from "@/components/design-system/Core/Button"

<Button variant="primary" size="md">Acknowledge Alert</Button>
<Button variant="ghost">Settings</Button>
```

### `Badge`
Used heavily to distinguish stream states across the UI.
```tsx
import { Badge } from "@/components/design-system/Core/Badge"

<Badge variant="success">LIVE</Badge>
<Badge variant="error" className="animate-pulse">ALERT</Badge>
```

### `Card`
For dashboard analytics panels.
```tsx
import { Card, CardHeader, CardTitle, CardContent } from "@/components/design-system/Core/Card"

<Card>
  <CardHeader><CardTitle>FPS</CardTitle></CardHeader>
  <CardContent>30.2</CardContent>
</Card>
```

### `Modal`
A cleanly animated (via `.screen-enter`) dialog wrapper.
```tsx
import { Modal } from "@/components/design-system/Core/Modal"

<Modal isOpen={open} onClose={() => setOpen(false)} title="Camera Config">
  <CameraForm />
</Modal>
```

### `Table` & `Input`
For CRUD operations mapped cleanly to the underlying PostgreSQL records logic.
```tsx
import { Input } from "@/components/design-system/Core/Input"
import { Table, TableRow, TableCell } from "@/components/design-system/Core/Table"

<Input placeholder="Enter RTSP URI" />
```

## 3. Video Processing Architecture

The video streaming leverages WebSockets rather than dragging down standard HTTP connections, ensuring synchronous display of UI overlays directly with bounding boxes.

- **`useWebSocket(url)`:** Initializes the singleton connection to `camera.frames` and `camera.tracking.updates`.
- **`useVideoStream(subscribe, stateRef, cameraId)`:** Reacts to updates for ONE specific camera. It uses `requestAnimationFrame` dropping rather than standard React state to prevent complete DOM thrashing on the 30FPS payloads.
- **`LiveVideoPlayer`:** Consumes the base64 JPEGs.
- **`OverlayLayer`:** Accepts `BoundingBox` scale locations from the backend (`[left, top, width, height]`), converting to dynamically resizing percentage-based CSS values seamlessly over exactly matching video pixels.
