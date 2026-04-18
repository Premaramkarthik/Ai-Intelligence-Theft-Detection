"use client";

import useSWR from "swr";

import { apiClient } from "@/services/apiClient";
import { endpoints } from "@/services/endpoints";
import type { HealthResponse } from "@/types/health";

export function useBackendHealth() {
  return useSWR("backend-health", () => apiClient.get<HealthResponse>(endpoints.health.root), {
    refreshInterval: 15_000,
  });
}

export function useProcessLogs(lines = 60) {
  return useSWR(["backend-logs", lines], () => apiClient.get<Record<string, string[]>>(endpoints.health.logs(lines)), {
    refreshInterval: 20_000,
  });
}

