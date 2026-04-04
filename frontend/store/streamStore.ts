"use client";

import { create } from "zustand";

import type {
  BackendLifecycleState,
  CameraResponse,
  PlaybackSnapshot,
  StreamCommandState,
  StreamInfoResponse,
  StreamTimelineEvent,
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
  return typeof value === "object" && value !== null && "stream_id" in value;
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
