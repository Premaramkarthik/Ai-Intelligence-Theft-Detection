"use client";

import { useEffect, useSyncExternalStore } from "react";

import { getRealtimeClient } from "@/services/realtimeClient";
import type { CameraRealtimeSnapshot, RealtimeOverviewSnapshot } from "@/types/realtime";

const EMPTY_OVERVIEW: RealtimeOverviewSnapshot = {
  connectionState: "disconnected",
  reconnectAttempt: 0,
  lastMessageAt: null,
  recentActivity: [],
  streamIds: [],
};

const EMPTY_CAMERA: CameraRealtimeSnapshot = {
  frame: null,
  tracking: null,
  inference: [],
  identity: [],
  lastUpdatedAt: null,
};

export function useRealtimeOverview(): RealtimeOverviewSnapshot {
  const client = getRealtimeClient();

  useEffect(() => {
    client.start();
  }, [client]);

  return useSyncExternalStore(
    client.subscribeOverview,
    client.getOverviewSnapshot,
    () => EMPTY_OVERVIEW,
  );
}

export function useCameraRealtime(cameraId: string): CameraRealtimeSnapshot {
  const client = getRealtimeClient();

  useEffect(() => {
    client.start();
  }, [client]);

  return useSyncExternalStore(
    (listener) => client.subscribeCamera(cameraId, listener),
    () => client.getCameraSnapshot(cameraId),
    () => EMPTY_CAMERA,
  );
}

