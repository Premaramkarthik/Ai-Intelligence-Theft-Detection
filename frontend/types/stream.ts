export type { ApiEnvelope as ApiResponse, PaginatedItems } from "@/types/api";
export type {
  CameraResponse,
  CreateCameraRequest,
  UpdateCameraRequest,
} from "@/types/camera";
export type { WebSocketEnvelope } from "@/types/realtime";

export interface InferenceConfigResponse {
  camera_id: string;
  enabled?: boolean;
  strategy?: string | null;
  worker_refresh_interval_seconds?: number;
}
