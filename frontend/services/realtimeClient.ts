"use client";

import { endpoints, getWebSocketUrl } from "@/services/endpoints";
import type {
  CameraFrameEvent,
  CameraRealtimeSnapshot,
  IdentityEvent,
  InferenceEvent,
  RealtimeActivityItem,
  RealtimeConnectionState,
  RealtimeOverviewSnapshot,
  TrackingEvent,
  WebSocketEnvelope,
} from "@/types/realtime";

type Listener = () => void;

const MAX_ACTIVITY_ITEMS = 30;
const MAX_INFERENCE_ITEMS = 12;
const MAX_IDENTITY_ITEMS = 12;
const ORPHAN_INFERENCE_TTL_MS = 3_000;
const INFERENCE_SWEEP_INTERVAL_MS = 1_000;

const EMPTY_CAMERA_SNAPSHOT: CameraRealtimeSnapshot = {
  frame: null,
  tracking: null,
  inference: [],
  identity: [],
  lastUpdatedAt: null,
};

function cloneCameraSnapshot(snapshot: CameraRealtimeSnapshot): CameraRealtimeSnapshot {
  return {
    frame: snapshot.frame,
    tracking: snapshot.tracking,
    inference: [...snapshot.inference],
    identity: [...snapshot.identity],
    lastUpdatedAt: snapshot.lastUpdatedAt,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function readCameraId(value: unknown): string | null {
  if (!isRecord(value)) {
    return null;
  }
  return typeof value.camera_id === "string" && value.camera_id ? value.camera_id : null;
}

function normalizeCameraId(envelope: WebSocketEnvelope<unknown>): string | null {
  const envelopeCameraId =
    typeof envelope.camera_id === "string" && envelope.camera_id ? envelope.camera_id : null;
  const payloadCameraId = readCameraId(envelope.data);

  if (envelopeCameraId && payloadCameraId && envelopeCameraId !== payloadCameraId) {
    return null;
  }
  return envelopeCameraId ?? payloadCameraId;
}

function isCameraPayload(payload: Record<string, unknown>, cameraId: string): boolean {
  return readCameraId(payload) === cameraId;
}

function isInferenceTopic(topic: string, payload: Record<string, unknown> | null): boolean {
  return topic === "camera.ai_results" || topic === "inference" || payload?.event === "inference.updated";
}

function isTrackingTopic(topic: string, payload: Record<string, unknown> | null): boolean {
  return topic === "camera.tracking.updates" || topic === "tracking.updated" || payload?.event === "tracking.updated";
}

function filterInferenceForCamera(events: InferenceEvent[], cameraId: string): InferenceEvent[] {
  return events.filter((event) => event.camera_id === cameraId);
}

function inferenceTrackKey(event: Pick<InferenceEvent, "persistent_id" | "local_track_id">): string {
  return event.persistent_id || event.local_track_id;
}

function upsertInferenceEvent(
  events: InferenceEvent[],
  event: InferenceEvent,
  cameraId: string,
): InferenceEvent[] {
  const eventKey = inferenceTrackKey(event);
  let replaced = false;
  const next = filterInferenceForCamera(events, cameraId).map((item) => {
    const sameLocalTrack = item.local_track_id === event.local_track_id;
    const samePersistentTrack = inferenceTrackKey(item) === eventKey;
    if (sameLocalTrack || samePersistentTrack) {
      replaced = true;
      return event;
    }
    return item;
  });

  if (!replaced) {
    next.push(event);
  }

  return next.length > MAX_INFERENCE_ITEMS
    ? next.slice(next.length - MAX_INFERENCE_ITEMS)
    : next;
}

function pruneInferenceToTracking(
  events: InferenceEvent[],
  tracking: TrackingEvent,
  cameraId: string,
): InferenceEvent[] {
  const localTrackIds = new Set(tracking.tracks.map((track) => track.track_id));
  const persistentIds = new Set(
    tracking.tracks
      .map((track) => track.persistent_id)
      .filter((value): value is string => typeof value === "string" && value.length > 0),
  );
  return filterInferenceForCamera(events, cameraId).filter((event) => {
    return localTrackIds.has(event.local_track_id) || persistentIds.has(event.persistent_id);
  });
}

function isInferenceAttachedToTracking(event: InferenceEvent, tracking: TrackingEvent | null): boolean {
  if (!tracking) {
    return false;
  }
  return tracking.tracks.some((track) => {
    if (track.track_id === event.local_track_id) {
      return true;
    }
    return Boolean(track.persistent_id) && track.persistent_id === event.persistent_id;
  });
}

function topicLabel(topic: string, payload: Record<string, unknown> | null): { label: string; tone: RealtimeActivityItem["tone"] } {
  if (isInferenceTopic(topic, payload)) {
    const level = typeof payload?.alert_level === "string" ? payload.alert_level : "normal";
    return {
      label:
        typeof payload?.label === "string"
          ? `Inference: ${payload.label}`
          : "Inference updated",
      tone: level === "alert" ? "critical" : level === "warning" ? "warning" : "positive",
    };
  }
  if (isTrackingTopic(topic, payload)) {
    return { label: "Tracking updated", tone: "positive" };
  }
  if (topic === "camera.frames") {
    return { label: "Frame received", tone: "neutral" };
  }
  if (topic === "identity.events") {
    return { label: "Identity lifecycle event", tone: "neutral" };
  }
  return { label: "Stream activity", tone: "neutral" };
}

class RealtimeClient {
  private socket: WebSocket | null = null;
  private connectionState: RealtimeConnectionState = "disconnected";
  private reconnectAttempt = 0;
  private reconnectTimer: number | null = null;
  private heartbeatTimer: number | null = null;
  private inferenceSweepTimer: number | null = null;
  private started = false;
  private lastMessageAt: string | null = null;
  private overviewListeners = new Set<Listener>();
  private cameraListeners = new Map<string, Set<Listener>>();
  private streamSnapshots = new Map<string, CameraRealtimeSnapshot>();
  private recentActivity: RealtimeActivityItem[] = [];

  // Cached snapshots — useSyncExternalStore requires getSnapshot to return the same
  // reference when data has not changed, otherwise React enters an infinite render loop.
  private cachedOverview: RealtimeOverviewSnapshot | null = null;
  private cachedCameraSnapshots = new Map<string, CameraRealtimeSnapshot>();

  start() {
    if (typeof window === "undefined" || this.started) {
      return;
    }
    this.started = true;
    this.open();
    this.inferenceSweepTimer = window.setInterval(
      () => this.sweepStaleInference(),
      INFERENCE_SWEEP_INTERVAL_MS,
    );
  }

  stop() {
    this.started = false;
    this.cachedOverview = null;
    this.cachedCameraSnapshots.clear();
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.inferenceSweepTimer !== null) {
      window.clearInterval(this.inferenceSweepTimer);
      this.inferenceSweepTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    this.setConnectionState("disconnected");
  }

  subscribeOverview = (listener: Listener) => {
    this.overviewListeners.add(listener);
    return () => {
      this.overviewListeners.delete(listener);
    };
  };

  subscribeCamera = (cameraId: string, listener: Listener) => {
    const bucket = this.cameraListeners.get(cameraId) ?? new Set<Listener>();
    bucket.add(listener);
    this.cameraListeners.set(cameraId, bucket);
    return () => {
      const current = this.cameraListeners.get(cameraId);
      if (!current) {
        return;
      }
      current.delete(listener);
      if (current.size === 0) {
        this.cameraListeners.delete(cameraId);
      }
    };
  };

  getOverviewSnapshot = (): RealtimeOverviewSnapshot => {
    if (!this.cachedOverview) {
      this.cachedOverview = {
        connectionState: this.connectionState,
        reconnectAttempt: this.reconnectAttempt,
        lastMessageAt: this.lastMessageAt,
        recentActivity: [...this.recentActivity],
        streamIds: Array.from(this.streamSnapshots.keys()),
      };
    }
    return this.cachedOverview;
  };

  getCameraSnapshot = (cameraId: string): CameraRealtimeSnapshot => {
    const cached = this.cachedCameraSnapshots.get(cameraId);
    if (cached) {
      return cached;
    }
    const snapshot = cloneCameraSnapshot(this.streamSnapshots.get(cameraId) ?? EMPTY_CAMERA_SNAPSHOT);
    this.cachedCameraSnapshots.set(cameraId, snapshot);
    return snapshot;
  };

  private open() {
    if (typeof window === "undefined") {
      return;
    }
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this.setConnectionState(this.reconnectAttempt > 0 ? "reconnecting" : "connecting");
    const wsUrl = getWebSocketUrl() || `${window.location.origin}${endpoints.streams.updates}`;

    let socket: WebSocket;
    try {
      socket = new WebSocket(wsUrl);
      this.socket = socket;
    } catch {
      this.scheduleReconnect();
      return;
    }

    socket.onopen = () => {
      if (socket !== this.socket) return;
      this.reconnectAttempt = 0;
      this.setConnectionState("connected");
      this.startHeartbeat();
    };

    socket.onmessage = (event) => {
      if (socket !== this.socket) return;
      this.handleMessage(event.data);
    };

    socket.onerror = () => {
      if (socket !== this.socket) return;
      this.setConnectionState("error");
    };

    socket.onclose = () => {
      if (socket !== this.socket) return;
      this.stopHeartbeat();
      if (this.started) {
        this.scheduleReconnect();
      } else {
        this.setConnectionState("disconnected");
      }
    };
  }

  private handleMessage(raw: string) {
    let envelope: WebSocketEnvelope<unknown>;
    try {
      envelope = JSON.parse(raw) as WebSocketEnvelope<unknown>;
    } catch {
      return;
    }

    this.lastMessageAt = new Date().toISOString();
    const cameraId = normalizeCameraId(envelope);
    const payload = isRecord(envelope.data) ? envelope.data : null;
    const topic = envelope.topic;

    if (cameraId && payload && isCameraPayload(payload, cameraId)) {
      const current = this.streamSnapshots.get(cameraId) ?? EMPTY_CAMERA_SNAPSHOT;
      const next = cloneCameraSnapshot(current);
      next.lastUpdatedAt = this.lastMessageAt;

      if (topic === "camera.frames" || payload.event === "camera.frame") {
        next.frame = payload as unknown as CameraFrameEvent;
      } else if (isTrackingTopic(topic, payload)) {
        const tracking = payload as unknown as TrackingEvent;
        next.tracking = tracking;
        next.inference = pruneInferenceToTracking(next.inference, tracking, cameraId);
      } else if (isInferenceTopic(topic, payload)) {
        next.inference = upsertInferenceEvent(
          next.inference,
          payload as unknown as InferenceEvent,
          cameraId,
        );
      } else if (topic === "identity.events") {
        next.identity = [
          payload as unknown as IdentityEvent,
          ...next.identity.filter((item) => {
            return !(
              item.local_track_id === payload.local_track_id &&
              item.occurred_at === payload.occurred_at
            );
          }),
        ].slice(0, MAX_IDENTITY_ITEMS);
      }

      this.streamSnapshots.set(cameraId, next);
      this.notifyCamera(cameraId);
      this.pushActivity(cameraId, topic, payload);
      this.notifyOverview();
      return;
    }

    this.notifyOverview();
  }

  private pushActivity(cameraId: string | null, topic: string, payload: Record<string, unknown> | null) {
    const activity = topicLabel(topic, payload);
    this.recentActivity = [
      {
        id: `${topic}-${cameraId ?? "global"}-${Date.now()}`,
        cameraId,
        topic,
        label: activity.label,
        tone: activity.tone,
        timestamp: new Date().toISOString(),
      },
      ...this.recentActivity,
    ].slice(0, MAX_ACTIVITY_ITEMS);
  }

  private sweepStaleInference() {
    const cutoff = Date.now() - ORPHAN_INFERENCE_TTL_MS;
    for (const [cameraId, snapshot] of this.streamSnapshots) {
      const fresh = snapshot.inference.filter(
        (ev) =>
          ev.camera_id === cameraId &&
          (isInferenceAttachedToTracking(ev, snapshot.tracking) ||
            new Date(ev.emitted_at).getTime() > cutoff),
      );
      if (fresh.length !== snapshot.inference.length) {
        const next = cloneCameraSnapshot(snapshot);
        next.inference = fresh;
        this.streamSnapshots.set(cameraId, next);
        this.notifyCamera(cameraId);
      }
    }
  }

  private scheduleReconnect() {
    if (typeof window === "undefined" || !this.started) {
      return;
    }
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
    }
    this.reconnectAttempt += 1;
    this.setConnectionState("reconnecting");
    const delay = Math.min(10_000, 1_000 * 2 ** Math.min(this.reconnectAttempt - 1, 3));
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, delay);
    this.notifyOverview();
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    if (typeof window === "undefined") {
      return;
    }
    this.heartbeatTimer = window.setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send("ping");
      }
    }, 15_000);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer !== null && typeof window !== "undefined") {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private setConnectionState(next: RealtimeConnectionState) {
    this.connectionState = next;
    this.notifyOverview();
  }

  private notifyOverview() {
    this.cachedOverview = null;
    for (const listener of this.overviewListeners) {
      listener();
    }
  }

  private notifyCamera(cameraId: string) {
    this.cachedCameraSnapshots.delete(cameraId);
    const listeners = this.cameraListeners.get(cameraId);
    if (!listeners) {
      return;
    }
    for (const listener of listeners) {
      listener();
    }
  }
}

let client: RealtimeClient | null = null;

export function getRealtimeClient(): RealtimeClient {
  if (client === null) {
    client = new RealtimeClient();
  }
  return client;
}
