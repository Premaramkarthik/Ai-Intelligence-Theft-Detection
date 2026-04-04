"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  BackendApiError,
  getStreamInfo,
  startStream,
  stopStream,
} from "@/lib/api";
import { StreamOrchestrator } from "@/media/orchestrator";
import { useStreamStore } from "@/store/streamStore";
import type {
  CameraResponse,
  PlaybackViewMode,
  StartStreamRequest,
  PlaybackSnapshot,
  StreamInfoResponse,
  StreamAccessUrls,
} from "@/types/stream";
import { useWebSocket } from "@/hooks/useWebSocket";

const RUNNABLE_BACKEND_STATES = new Set([
  "starting",
  "running",
  "reconnecting",
] as const);

function isRunnableBackendState(
  state: string,
): state is "starting" | "running" | "reconnecting" {
  return RUNNABLE_BACKEND_STATES.has(
    state as "starting" | "running" | "reconnecting",
  );
}

/**
 * Convert API and runtime failures into readable control-surface copy.
 */
function toActionErrorMessage(error: unknown): string {
  if (error instanceof BackendApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "The stream command could not be completed.";
}

const IDLE_PLAYBACK_SNAPSHOT: PlaybackSnapshot = {
  playbackState: "idle",
  playbackProtocol: null,
  playbackMessage: null,
  playbackError: null,
};

/**
 * Build a consistent backend start request for all camera-page entry points.
 */
function buildStartRequest(
  sampleFps: number | undefined,
  forceRestart: boolean,
  reason: string,
): StartStreamRequest {
  return {
    force_restart: forceRestart,
    requested_protocol: "webrtc",
    sample_fps: sampleFps ?? 5,
    enable_tracking_events: true,
    reason,
  };
}

interface UseStreamOptions {
  initialCamera?: CameraResponse | null;
  initialStreamInfo?: StreamInfoResponse | null;
  autoStart?: boolean;
  sampleFps?: number;
}

export function useStream(
  cameraId: string,
  options: UseStreamOptions = {},
) {
  const attachedVideoElementRef = useRef<HTMLVideoElement | null>(null);
  const orchestratorRef = useRef<StreamOrchestrator | null>(null);
  const playbackActivationRef = useRef(false);
  const selectedSourceKeyRef = useRef<string | null>(null);
  const routeSyncRequestRef = useRef(0);
  const [videoElement, setVideoElement] = useState<HTMLVideoElement | null>(null);
  const [sourceSelectionTouched, setSourceSelectionTouched] =
    useState(false);
  const [preferredPlaybackViewMode, setPreferredPlaybackViewMode] =
    useState<PlaybackViewMode>("raw");

  const camera = useStreamStore((state) => state.cameras[cameraId]);
  const streamState = useStreamStore((state) => state.streams[cameraId]);
  const upsertCamera = useStreamStore((state) => state.upsertCamera);
  const upsertStreamInfo = useStreamStore((state) => state.upsertStreamInfo);
  const setCommandState = useStreamStore((state) => state.setCommandState);
  const clearCommandState = useStreamStore((state) => state.clearCommandState);
  const setPlaybackSnapshot = useStreamStore(
    (state) => state.setPlaybackSnapshot,
  );

  useEffect(() => {
    if (options.initialCamera) {
      upsertCamera(options.initialCamera);
    }
    if (options.initialStreamInfo) {
      upsertStreamInfo(options.initialStreamInfo);
    }
  }, [options.initialCamera, options.initialStreamInfo, upsertCamera, upsertStreamInfo]);

  const activeCamera = camera ?? options.initialCamera ?? null;
  const activeStream = streamState?.streamInfo ?? options.initialStreamInfo ?? null;
  const activeBackendLifecycle =
    streamState?.backendLifecycle ??
    activeCamera?.stream_status ??
    "stopped";
  const activeCommandState = streamState?.commandState ?? "idle";
  const activeCommandMessage = streamState?.commandMessage ?? null;
  const activeTrackingState = activeStream?.tracking ?? null;
  const trackingAvailable = Boolean(
    activeTrackingState?.enabled &&
    activeTrackingState.access_urls?.webrtc_url &&
    activeTrackingState.access_urls?.hls_url,
  );
  const playbackViewMode: PlaybackViewMode =
    sourceSelectionTouched
      ? preferredPlaybackViewMode === "tracked" && !trackingAvailable
        ? "raw"
        : preferredPlaybackViewMode
      : "raw";

  const selectedAccessUrls: StreamAccessUrls | null =
    playbackViewMode === "tracked" && trackingAvailable
      ? activeTrackingState?.access_urls ?? null
      : activeStream?.access_urls ?? null;

  const setVideoRef = useCallback((node: HTMLVideoElement | null) => {
    if (node === null) {
      attachedVideoElementRef.current = null;
      playbackActivationRef.current = false;
    }
    setVideoElement(node);
  }, []);

  const ensureOrchestrator = useCallback((): StreamOrchestrator | null => {
    if (!videoElement) {
      return null;
    }

    if (!orchestratorRef.current) {
      orchestratorRef.current = new StreamOrchestrator({
        onPlaybackSnapshot: (snapshot: PlaybackSnapshot) => {
          setPlaybackSnapshot(cameraId, snapshot);
        },
      });
    }

    if (attachedVideoElementRef.current !== videoElement) {
      orchestratorRef.current.attach(videoElement);
      attachedVideoElementRef.current = videoElement;
    }

    return orchestratorRef.current;
  }, [cameraId, setPlaybackSnapshot, videoElement]);

  useWebSocket(cameraId, activeStream?.websocket_url ?? null);

  /**
   * Apply a backend start request without prematurely flagging playback as booted.
   */
  const requestBackendStart = useCallback(async (
    forceRestart: boolean,
    commandState: "starting" | "restarting",
    commandMessage: string,
    reason: string,
  ): Promise<StreamInfoResponse> => {
    setCommandState(cameraId, commandState, commandMessage);
    const streamInfo = await startStream(
      cameraId,
      buildStartRequest(options.sampleFps, forceRestart, reason),
    );
    upsertStreamInfo(streamInfo);
    return streamInfo;
  }, [cameraId, options.sampleFps, setCommandState, upsertStreamInfo]);

  /**
   * Re-sync the camera page with backend truth whenever the route becomes active.
   */
  const syncRouteEntryState = useCallback(async (): Promise<void> => {
    const requestId = routeSyncRequestRef.current + 1;
    routeSyncRequestRef.current = requestId;

    try {
      if (options.autoStart) {
        await requestBackendStart(
          false,
          "starting",
          "Connecting to live playback.",
          "frontend_route_entry",
        );
      } else {
        const streamInfo = await getStreamInfo(cameraId);
        if (requestId !== routeSyncRequestRef.current || !streamInfo) {
          return;
        }
        upsertStreamInfo(streamInfo);
      }
    } catch (error) {
      if (requestId !== routeSyncRequestRef.current) {
        return;
      }
      clearCommandState(cameraId);
      throw error;
    }
  }, [
    cameraId,
    clearCommandState,
    options.autoStart,
    requestBackendStart,
    upsertStreamInfo,
  ]);

  const refresh = async () => {
    setCommandState(cameraId, "refreshing", "Refreshing backend state.");
    try {
      const streamInfo = await getStreamInfo(cameraId);
      if (streamInfo) {
        upsertStreamInfo(streamInfo);
      } else {
        clearCommandState(cameraId);
      }
    } catch (error) {
      clearCommandState(cameraId);
      throw new Error(toActionErrorMessage(error));
    }
  };

  const start = async (forceRestart = false) => {
    playbackActivationRef.current = false;
    if (forceRestart) {
      await orchestratorRef.current?.stop();
    }
    try {
      await requestBackendStart(
        forceRestart,
        forceRestart ? "restarting" : "starting",
        forceRestart
          ? "Requesting a controlled reconnect from the backend."
          : "Requesting live stream startup from the backend.",
        forceRestart ? "frontend_force_restart_request" : "frontend_start_request",
      );
    } catch (error) {
      clearCommandState(cameraId);
      throw new Error(toActionErrorMessage(error));
    }
  };

  const stop = async () => {
    setCommandState(cameraId, "stopping", "Requesting stream shutdown.");
    playbackActivationRef.current = false;
    await orchestratorRef.current?.stop();
    try {
      const streamInfo = await stopStream(cameraId, {
        reason: "frontend_stop_request",
      });
      upsertStreamInfo(streamInfo);
    } catch (error) {
      clearCommandState(cameraId);
      throw new Error(toActionErrorMessage(error));
    }
  };

  const retryPlayback = async () => {
    const orchestrator = ensureOrchestrator();
    if (!orchestrator) {
      return;
    }
    playbackActivationRef.current = true;
    if (selectedAccessUrls) {
      orchestrator.setSources({
        webrtcUrl: selectedAccessUrls.webrtc_url,
        hlsUrl: selectedAccessUrls.hls_url,
      });
    }
    await orchestrator.reconnect();
  };

  useEffect(() => {
    ensureOrchestrator();
  }, [ensureOrchestrator]);

  useEffect(() => {
    return () => {
      routeSyncRequestRef.current += 1;
      playbackActivationRef.current = false;
      selectedSourceKeyRef.current = null;
      attachedVideoElementRef.current = null;
      setPlaybackSnapshot(cameraId, IDLE_PLAYBACK_SNAPSHOT);
      void orchestratorRef.current?.stop();
      orchestratorRef.current = null;
    };
  }, [cameraId, setPlaybackSnapshot]);

  useEffect(() => {
    void syncRouteEntryState().catch(() => undefined);
    return () => {
      routeSyncRequestRef.current += 1;
    };
  }, [
    syncRouteEntryState,
  ]);

  useEffect(() => {
    const orchestrator = ensureOrchestrator();
    if (!orchestrator || !selectedAccessUrls) {
      return;
    }

    const selectedSourceKey = [
      playbackViewMode,
      selectedAccessUrls.webrtc_url,
      selectedAccessUrls.hls_url,
    ].join("|");
    const sourceChanged = selectedSourceKeyRef.current !== selectedSourceKey;
    selectedSourceKeyRef.current = selectedSourceKey;

    orchestrator.setSources({
      webrtcUrl: selectedAccessUrls.webrtc_url,
      hlsUrl: selectedAccessUrls.hls_url,
    });

    if (!isRunnableBackendState(activeBackendLifecycle)) {
      playbackActivationRef.current = false;
      selectedSourceKeyRef.current = null;
      void orchestrator.stop();
      return;
    }

    if (playbackActivationRef.current && !sourceChanged) {
      return;
    }

    playbackActivationRef.current = true;
    void orchestrator.start();
  }, [
    activeBackendLifecycle,
    cameraId,
    ensureOrchestrator,
    playbackViewMode,
    selectedAccessUrls,
  ]);

  const runAction = (work: () => Promise<void>) => {
    if (activeCommandState !== "idle") {
      return;
    }
    void work().catch(() => undefined);
  };

  return {
    camera: activeCamera,
    streamInfo: activeStream,
    trackingInfo: activeTrackingState,
    videoElement,
    playbackViewMode,
    backendLifecycle: activeBackendLifecycle,
    commandState: activeCommandState,
    commandMessage: activeCommandMessage,
    playbackState: streamState?.playbackState ?? "idle",
    playbackProtocol: streamState?.playbackProtocol ?? null,
    playbackMessage: streamState?.playbackMessage ?? null,
    playbackError: streamState?.playbackError ?? null,
    timeline: streamState?.timeline ?? [],
    isPending: activeCommandState !== "idle",
    videoRef: setVideoRef,
    refresh: () => runAction(refresh),
    retryPlayback,
    setPlaybackViewMode: (viewMode: PlaybackViewMode) => {
      setSourceSelectionTouched(true);
      setPreferredPlaybackViewMode(viewMode);
    },
    isTrackedPlaybackAvailable: trackingAvailable,
    start: () => runAction(() => start(false)),
    forceRestart: () => runAction(() => start(true)),
    stop: () => runAction(stop),
  };
}
