"use client";

import { create } from "zustand";

import type {
  BackendLifecycleState,
  CameraResponse,
  InferenceAlertEnvelopeData,
  InferenceEvent,
  InferenceStateResponse,
  PlaybackSnapshot,
  StreamCommandState,
  StreamInfoResponse,
  StreamTimelineEvent,
  TrackingStateResponse,
  TrackingTrackResponse,
  TrackingUpdateEnvelopeData,
  WebSocketEnvelope,
} from "@/types/stream";

interface StreamEntityState {
  streamInfo: StreamInfoResponse | null;
  backendLifecycle: BackendLifecycleState;
  commandState: StreamCommandState;
  commandMessage: string | null;
  commandError: string | null;
  playbackState: PlaybackSnapshot["playbackState"];
  playbackProtocol: PlaybackSnapshot["playbackProtocol"];
  playbackMessage: string | null;
  playbackError: string | null;
  inferenceActiveEvents: InferenceEvent[];
  recentInferenceAlerts: InferenceEvent[];
  timeline: StreamTimelineEvent[];
}

interface StreamStoreState {
  cameras: Record<string, CameraResponse>;
  cameraOrder: string[];
  streams: Record<string, StreamEntityState>;
  hydrateCameras: (cameras: CameraResponse[]) => void;
  upsertCamera: (camera: CameraResponse) => void;
  removeCamera: (cameraId: string) => void;
  upsertStreamInfo: (streamInfo: StreamInfoResponse) => void;
  applyWebSocketEnvelope: (envelope: WebSocketEnvelope) => void;
  setCommandState: (
    cameraId: string,
    commandState: StreamCommandState,
    commandMessage: string,
  ) => void;
  clearCommandState: (cameraId: string) => void;
  setPlaybackSnapshot: (
    cameraId: string,
    snapshot: PlaybackSnapshot,
  ) => void;
  applyInferenceEnvelope: (envelope: WebSocketEnvelope) => void;
  pruneInferenceEvents: (ttlMs: number) => void;
  clearCameraStream: (cameraId: string) => void;
}

const MAX_TIMELINE_ITEMS = 20;
let timelineSequence = 0;

function createInitialStreamState(
  backendLifecycle: BackendLifecycleState = "stopped",
): StreamEntityState {
  return {
    streamInfo: null,
    backendLifecycle,
    commandState: "idle",
    commandMessage: null,
    commandError: null,
    playbackState: "idle",
    playbackProtocol: null,
    playbackMessage: null,
    playbackError: null,
    inferenceActiveEvents: [],
    recentInferenceAlerts: [],
    timeline: [],
  };
}

/**
 * Clear transient command UI once backend updates confirm the requested state.
 */
function reconcileCommandState(
  current: StreamEntityState,
  streamInfo: StreamInfoResponse,
  envelopeTopic?: string,
): Pick<StreamEntityState, "commandState" | "commandMessage" | "commandError"> {
  const commandState = current.commandState;
  const connectedEvent = envelopeTopic === "stream_connected";
  const workerReady =
    streamInfo.worker.current_fps > 0 || streamInfo.worker.sampled_frames > 0;

  if (commandState === "starting" || commandState === "restarting") {
    if (
      connectedEvent ||
      workerReady ||
      streamInfo.status === "error" ||
      streamInfo.status === "crashed" ||
      streamInfo.status === "stopped"
    ) {
      return {
        commandState: "idle",
        commandMessage: null,
        commandError: null,
      };
    }
  }

  if (commandState === "stopping" && streamInfo.status === "stopped") {
    return {
      commandState: "idle",
      commandMessage: null,
      commandError: null,
    };
  }

  if (commandState === "refreshing") {
    return {
      commandState: "idle",
      commandMessage: null,
      commandError: null,
    };
  }

  return {
    commandState: current.commandState,
    commandMessage: current.commandMessage,
    commandError: current.commandError,
  };
}

function appendTimeline(
  timeline: StreamTimelineEvent[],
  event: Omit<StreamTimelineEvent, "id">,
): StreamTimelineEvent[] {
  timelineSequence += 1;
  return [
    {
      id: `${event.timestamp}-${event.topic}-${timelineSequence}`,
      ...event,
    },
    ...timeline,
  ].slice(0, MAX_TIMELINE_ITEMS);
}

function isStreamInfoResponse(value: unknown): value is StreamInfoResponse {
  if (typeof value !== "object" || value === null || !("stream_id" in value)) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    !("inference" in candidate) ||
    candidate.inference === null ||
    isInferenceStateResponse(candidate.inference)
  );
}

function isStreamSnapshot(
  value: unknown,
): value is { items: StreamInfoResponse[] } {
  return (
    typeof value === "object" &&
    value !== null &&
    "items" in value &&
    Array.isArray((value as { items: unknown[] }).items)
  );
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isTrackingTrackResponse(value: unknown): value is TrackingTrackResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.track_id === "string" &&
    (candidate.persistent_id === null || typeof candidate.persistent_id === "string") &&
    (candidate.class_name === null || typeof candidate.class_name === "string") &&
    isFiniteNumber(candidate.confidence) &&
    (candidate.similarity === null || isFiniteNumber(candidate.similarity)) &&
    isFiniteNumber(candidate.left) &&
    isFiniteNumber(candidate.top) &&
    isFiniteNumber(candidate.width) &&
    isFiniteNumber(candidate.height)
  );
}

function isTrackingUpdateEnvelopeData(
  value: unknown,
): value is TrackingUpdateEnvelopeData {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    (!("stream_name" in candidate) ||
      candidate.stream_name === null ||
      typeof candidate.stream_name === "string") &&
    (!("annotated_stream_name" in candidate) ||
      candidate.annotated_stream_name === null ||
      typeof candidate.annotated_stream_name === "string") &&
    (!("active_tracks" in candidate) || isFiniteNumber(candidate.active_tracks)) &&
    (!("tracks" in candidate) ||
      (Array.isArray(candidate.tracks) &&
        candidate.tracks.every(isTrackingTrackResponse)))
  );
}

function isInferenceStateResponse(value: unknown): value is InferenceStateResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.enabled === "boolean" &&
    (candidate.strategy === null || typeof candidate.strategy === "string") &&
    Array.isArray(candidate.available_strategies) &&
    candidate.available_strategies.every((item) => typeof item === "string") &&
    typeof candidate.healthy === "boolean" &&
    (candidate.last_error_message === null ||
      typeof candidate.last_error_message === "string") &&
    isFiniteNumber(candidate.queue_depth) &&
    isFiniteNumber(candidate.active_tracks) &&
    (candidate.last_result_at === null ||
      typeof candidate.last_result_at === "string")
  );
}

function isInferenceEvent(value: unknown): value is InferenceEvent {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.camera_id === "string" &&
    typeof candidate.stream_name === "string" &&
    typeof candidate.persistent_id === "string" &&
    typeof candidate.local_track_id === "string" &&
    typeof candidate.strategy === "string" &&
    isFiniteNumber(candidate.score) &&
    typeof candidate.alert_level === "string" &&
    typeof candidate.label === "string" &&
    typeof candidate.model_name === "string" &&
    typeof candidate.sampled_at === "string" &&
    typeof candidate.emitted_at === "string"
  );
}

function isInferenceAlertEnvelopeData(
  value: unknown,
): value is InferenceAlertEnvelopeData {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.alert_level === "string" &&
    typeof candidate.persistent_id === "string" &&
    typeof candidate.camera_id === "string" &&
    isFiniteNumber(candidate.score) &&
    typeof candidate.strategy === "string"
  );
}

function buildInferenceEventId(event: InferenceEvent): string {
  return [
    event.camera_id,
    event.persistent_id,
    event.local_track_id,
    event.emitted_at,
    event.label,
    event.model_name,
    event.score,
  ].join("|");
}

function buildInferenceTrackKey(event: InferenceEvent): string {
  return `${event.persistent_id}|${event.local_track_id}`;
}

function sortInferenceEvents(events: InferenceEvent[]): InferenceEvent[] {
  return [...events].sort((left, right) => {
    return Date.parse(right.emitted_at) - Date.parse(left.emitted_at);
  });
}

function upsertActiveInferenceEvent(
  current: InferenceEvent[],
  nextEvent: InferenceEvent,
): InferenceEvent[] {
  const nextTrackKey = buildInferenceTrackKey(nextEvent);
  const deduped = current.filter((event) => {
    return buildInferenceTrackKey(event) !== nextTrackKey;
  });
  return sortInferenceEvents([nextEvent, ...deduped]);
}

function appendRecentInferenceAlert(
  current: InferenceEvent[],
  nextEvent: InferenceEvent,
): InferenceEvent[] {
  const nextEventId = buildInferenceEventId(nextEvent);
  return [
    nextEvent,
    ...current.filter((event) => buildInferenceEventId(event) !== nextEventId),
  ].slice(0, MAX_TIMELINE_ITEMS);
}

function pruneExpiredInferenceEvents(
  current: InferenceEvent[],
  cutoffTimestampMs: number,
): InferenceEvent[] {
  return current.filter((event) => Date.parse(event.emitted_at) >= cutoffTimestampMs);
}

function mergeTrackingState(
  current: TrackingStateResponse | null | undefined,
  update: TrackingUpdateEnvelopeData,
): TrackingStateResponse {
  const tracks = update.tracks ?? [];
  return {
    enabled: true,
    stream_name:
      update.annotated_stream_name ??
      update.stream_name ??
      current?.stream_name ??
      null,
    access_urls: current?.access_urls ?? null,
    is_registered: current?.is_registered ?? true,
    is_process_alive: current?.is_process_alive ?? true,
    reconnect_attempts: current?.reconnect_attempts ?? 0,
    active_tracks: update.active_tracks ?? tracks.length,
    identity_backend: current?.identity_backend ?? "milvus",
    last_error_message: current?.last_error_message ?? null,
    tracks,
  };
}

function mergeInferenceState(
  current: InferenceStateResponse | null | undefined,
  options: {
    event?: InferenceEvent;
    alert?: InferenceAlertEnvelopeData;
    activeTrackCount?: number;
  } = {},
): InferenceStateResponse {
  const strategy =
    options.event?.strategy ??
    options.alert?.strategy ??
    current?.strategy ??
    null;
  return {
    enabled: true,
    strategy,
    available_strategies: current?.available_strategies ?? [],
    healthy: true,
    last_error_message: current?.last_error_message ?? null,
    queue_depth: current?.queue_depth ?? 0,
    active_tracks: options.activeTrackCount ?? current?.active_tracks ?? 0,
    last_result_at:
      options.event?.emitted_at ??
      current?.last_result_at ??
      null,
  };
}

function applyInferenceEnvelopeToStreams(
  streams: Record<string, StreamEntityState>,
  envelope: WebSocketEnvelope,
): Record<string, StreamEntityState> | null {
  if (!envelope.camera_id) {
    return null;
  }

  const current = streams[envelope.camera_id] ?? createInitialStreamState();
  const timeline = appendTimeline(current.timeline, {
    type: envelope.type,
    topic: envelope.topic,
    message: envelope.message,
    timestamp: envelope.timestamp,
  });

  if (envelope.type === "inference.updated" && isInferenceEvent(envelope.data)) {
    const nextActiveEvents = upsertActiveInferenceEvent(
      current.inferenceActiveEvents,
      envelope.data,
    );
    const nextRecentAlerts =
      envelope.data.alert_level === "normal"
        ? current.recentInferenceAlerts
        : appendRecentInferenceAlert(current.recentInferenceAlerts, envelope.data);

    return {
      ...streams,
      [envelope.camera_id]: {
        ...current,
        streamInfo: current.streamInfo
          ? {
              ...current.streamInfo,
              inference: mergeInferenceState(current.streamInfo.inference, {
                event: envelope.data,
                activeTrackCount: nextActiveEvents.length,
              }),
            }
          : current.streamInfo,
        inferenceActiveEvents: nextActiveEvents,
        recentInferenceAlerts: nextRecentAlerts,
        timeline,
      },
    };
  }

  if (envelope.type === "inference.alert" && isInferenceAlertEnvelopeData(envelope.data)) {
    return {
      ...streams,
      [envelope.camera_id]: {
        ...current,
        streamInfo: current.streamInfo
          ? {
              ...current.streamInfo,
              inference: mergeInferenceState(current.streamInfo.inference, {
                alert: envelope.data,
                activeTrackCount: current.inferenceActiveEvents.length,
              }),
            }
          : current.streamInfo,
        timeline,
      },
    };
  }

  return null;
}


export const useStreamStore = create<StreamStoreState>((set) => ({
  cameras: {},
  cameraOrder: [],
  streams: {},
  hydrateCameras: (cameras) =>
    set((state) => {
      const nextCameras = { ...state.cameras };
      const nextStreams = { ...state.streams };

      cameras.forEach((camera) => {
        nextCameras[camera.id] = camera;
        nextStreams[camera.id] =
          nextStreams[camera.id] ??
          createInitialStreamState(camera.stream_status ?? "stopped");
        nextStreams[camera.id].backendLifecycle =
          nextStreams[camera.id].streamInfo?.status ??
          camera.stream_status ??
          "stopped";
      });

      return {
        cameras: nextCameras,
        cameraOrder: cameras.map((camera) => camera.id),
        streams: nextStreams,
      };
    }),
  upsertCamera: (camera) =>
    set((state) => ({
      cameras: {
        ...state.cameras,
        [camera.id]: camera,
      },
      cameraOrder: state.cameraOrder.includes(camera.id)
        ? state.cameraOrder
        : [...state.cameraOrder, camera.id],
      streams: {
        ...state.streams,
        [camera.id]:
          state.streams[camera.id] ??
          createInitialStreamState(camera.stream_status ?? "stopped"),
      },
    })),
  removeCamera: (cameraId) =>
    set((state) => {
      const nextCameras = { ...state.cameras };
      const nextStreams = { ...state.streams };
      delete nextCameras[cameraId];
      delete nextStreams[cameraId];

      return {
        cameras: nextCameras,
        cameraOrder: state.cameraOrder.filter((id) => id !== cameraId),
        streams: nextStreams,
      };
    }),
  upsertStreamInfo: (streamInfo) =>
    set((state) => {
      const current = state.streams[streamInfo.camera_id] ??
        createInitialStreamState(streamInfo.status);
      const nextCommandState = reconcileCommandState(current, streamInfo);
      return {
        streams: {
          ...state.streams,
          [streamInfo.camera_id]: {
            ...current,
            ...nextCommandState,
            streamInfo,
            backendLifecycle: streamInfo.status,
            timeline: appendTimeline(current.timeline, {
              type: "stream.updated",
              topic: "stream.updated",
              message: `Backend status is ${streamInfo.status}.`,
              timestamp: streamInfo.updated_at ?? new Date().toISOString(),
            }),
          },
        },
      };
    }),
  applyWebSocketEnvelope: (envelope) =>
    set((state) => {
      const nextStreams = { ...state.streams };

      if (isStreamSnapshot(envelope.data)) {
        envelope.data.items.forEach((item) => {
          if (!isStreamInfoResponse(item)) {
            return;
          }
          const current = nextStreams[item.camera_id] ??
            createInitialStreamState(item.status);
          const nextCommandState = reconcileCommandState(
            current,
            item,
            envelope.topic,
          );
          nextStreams[item.camera_id] = {
            ...current,
            ...nextCommandState,
            streamInfo: item,
            backendLifecycle: item.status,
            timeline: appendTimeline(current.timeline, {
              type: envelope.type,
              topic: envelope.topic,
              message: envelope.message,
              timestamp: envelope.timestamp,
            }),
          };
        });

        return { streams: nextStreams };
      }

      if (envelope.camera_id && isStreamInfoResponse(envelope.data)) {
        const current = nextStreams[envelope.camera_id] ??
          createInitialStreamState(envelope.data.status);
        const nextCommandState = reconcileCommandState(
          current,
          envelope.data,
          envelope.topic,
        );
        nextStreams[envelope.camera_id] = {
          ...current,
          ...nextCommandState,
          streamInfo: envelope.data,
          backendLifecycle: envelope.data.status,
          timeline: appendTimeline(current.timeline, {
            type: envelope.type,
            topic: envelope.topic,
            message: envelope.message,
            timestamp: envelope.timestamp,
          }),
        };
        return { streams: nextStreams };
      }

      if (
        envelope.camera_id &&
        envelope.topic === "tracking.updated" &&
        isTrackingUpdateEnvelopeData(envelope.data)
      ) {
        const current = nextStreams[envelope.camera_id] ??
          createInitialStreamState();
        const timeline = appendTimeline(current.timeline, {
          type: envelope.type,
          topic: envelope.topic,
          message: envelope.message,
          timestamp: envelope.timestamp,
        });

        if (!current.streamInfo) {
          nextStreams[envelope.camera_id] = {
            ...current,
            timeline,
          };
          return { streams: nextStreams };
        }

        nextStreams[envelope.camera_id] = {
          ...current,
          streamInfo: {
            ...current.streamInfo,
            tracking: mergeTrackingState(
              current.streamInfo.tracking,
              envelope.data,
            ),
          },
          timeline,
        };
        return { streams: nextStreams };
      }

      const nextInferenceStreams = applyInferenceEnvelopeToStreams(
        nextStreams,
        envelope,
      );
      if (nextInferenceStreams) {
        return { streams: nextInferenceStreams };
      }

      return state;
    }),
  setCommandState: (cameraId, commandState, commandMessage) =>
    set((state) => {
      const current = state.streams[cameraId] ?? createInitialStreamState();
      return {
        streams: {
          ...state.streams,
          [cameraId]: {
            ...current,
            commandState,
            commandMessage,
            commandError: null,
          },
        },
      };
    }),
  clearCommandState: (cameraId) =>
    set((state) => {
      const current = state.streams[cameraId] ?? createInitialStreamState();
      return {
        streams: {
          ...state.streams,
          [cameraId]: {
            ...current,
            commandState: "idle",
            commandMessage: null,
            commandError: null,
          },
        },
      };
    }),
  setPlaybackSnapshot: (cameraId, snapshot) =>
    set((state) => {
      const current = state.streams[cameraId] ?? createInitialStreamState();
      return {
        streams: {
          ...state.streams,
          [cameraId]: {
            ...current,
            playbackState: snapshot.playbackState,
            playbackProtocol: snapshot.playbackProtocol,
            playbackMessage: snapshot.playbackMessage,
            playbackError: snapshot.playbackError,
          },
        },
      };
    }),
  applyInferenceEnvelope: (envelope) =>
    set((state) => {
      const nextStreams = applyInferenceEnvelopeToStreams(state.streams, envelope);
      if (!nextStreams) {
        return state;
      }
      return { streams: nextStreams };
    }),
  pruneInferenceEvents: (ttlMs) =>
    set((state) => {
      const cutoffTimestampMs = Date.now() - ttlMs;
      let changed = false;
      const nextStreams = Object.fromEntries(
        Object.entries(state.streams).map(([cameraId, streamState]) => {
          const nextActiveEvents = pruneExpiredInferenceEvents(
            streamState.inferenceActiveEvents,
            cutoffTimestampMs,
          );
          if (nextActiveEvents.length !== streamState.inferenceActiveEvents.length) {
            changed = true;
          }
          return [
            cameraId,
            nextActiveEvents.length === streamState.inferenceActiveEvents.length
              ? streamState
              : {
                  ...streamState,
                  streamInfo: streamState.streamInfo
                    ? {
                        ...streamState.streamInfo,
                        inference: streamState.streamInfo.inference
                          ? {
                              ...streamState.streamInfo.inference,
                              active_tracks: nextActiveEvents.length,
                            }
                          : streamState.streamInfo.inference,
                      }
                    : streamState.streamInfo,
                  inferenceActiveEvents: nextActiveEvents,
                },
          ];
        }),
      ) as Record<string, StreamEntityState>;

      if (!changed) {
        return state;
      }

      return {
        streams: nextStreams,
      };
    }),
  clearCameraStream: (cameraId) =>
    set((state) => ({
      streams: {
        ...state.streams,
        [cameraId]: createInitialStreamState(
          state.cameras[cameraId]?.stream_status ?? "stopped",
        ),
      },
    })),
}));
