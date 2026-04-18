"use client";

import useSWR from "swr";

import { useCameraRealtime, useRealtimeOverview } from "@/hooks/useRealtime";
import * as streamApi from "@/modules/streams/api";

export function useStreamHealth() {
  return useSWR("stream-health", streamApi.getStreamHealth, {
    refreshInterval: 15_000,
  });
}

export { useCameraRealtime, useRealtimeOverview };

