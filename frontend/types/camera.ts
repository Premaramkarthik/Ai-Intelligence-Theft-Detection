export type CameraStatus = "active" | "inactive" | "error";
export type RTSPTransport = "tcp" | "udp";
export type ValidationStatus =
  | "pending"
  | "reachable"
  | "unreachable"
  | "auth_failed"
  | "timeout"
  | "error";

export interface CameraResponse {
  id: string;
  name: string;
  location: string | null;
  host: string | null;
  port: number | null;
  path: string | null;
  source_mode: string;
  rtsp_url_preview: string;
  transport: RTSPTransport;
  status: CameraStatus;
  stream_status?: string | null;
  has_credentials: boolean;
  metadata: Record<string, unknown>;
  tags: string[];
  last_validated_at: string | null;
  last_validation_status: ValidationStatus;
  last_validation_message: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CameraValidationResponse {
  camera_id: string;
  camera_name: string;
  is_reachable: boolean;
  code: string;
  message: string;
  resolved_rtsp_url_preview: string;
  latency_ms: number | null;
  details?: Record<string, unknown> | null;
  validated_at: string;
}

export interface CreateCameraRequest {
  name: string;
  location: string | null;
  host: string | null;
  port: number;
  username: string | null;
  password?: string | null;
  path: string | null;
  direct_rtsp_url: string | null;
  transport: RTSPTransport;
  status: CameraStatus;
  metadata: Record<string, unknown>;
  tags: string[];
}

export type UpdateCameraRequest = Partial<CreateCameraRequest>;
