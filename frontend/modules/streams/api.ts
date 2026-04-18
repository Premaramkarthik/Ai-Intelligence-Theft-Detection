import { apiClient } from "@/services/apiClient";
import { endpoints } from "@/services/endpoints";
import type { InferenceConfigResponse } from "@/types/stream";
import type { StreamHealthResponse } from "@/types/health";

export function patchInference(cameraId: string, payload: { enabled?: boolean; strategy?: string | null }) {
  return apiClient.patch<InferenceConfigResponse>(endpoints.streams.inference(cameraId), payload);
}

export function getStreamHealth() {
  return apiClient.get<StreamHealthResponse>(endpoints.streams.health);
}

