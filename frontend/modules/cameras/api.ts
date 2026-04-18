import { apiClient } from "@/services/apiClient";
import { endpoints } from "@/services/endpoints";
import type {
  CameraResponse,
  CameraValidationResponse,
  CreateCameraRequest,
} from "@/types/camera";
import type { PaginatedItems } from "@/types/api";

export function listCameras(params?: {
  page?: number;
  page_size?: number;
  search?: string;
  status?: "active" | "inactive" | "error" | "all";
}) {
  return apiClient.get<PaginatedItems<CameraResponse>>(endpoints.cameras.list(params));
}

export function getCamera(cameraId: string) {
  return apiClient.get<CameraResponse>(endpoints.cameras.detail(cameraId));
}

export function createCamera(payload: CreateCameraRequest) {
  return apiClient.post<CameraResponse>(endpoints.cameras.create, payload);
}

export function deleteCamera(cameraId: string) {
  return apiClient.delete<{ id: string }>(endpoints.cameras.detail(cameraId));
}

export function validateCamera(cameraId: string, timeout_seconds?: number) {
  return apiClient.post<CameraValidationResponse>(
    endpoints.cameras.validate(cameraId),
    timeout_seconds ? { timeout_seconds } : {},
  );
}

