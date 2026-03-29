export type ApiStatus = "success" | "error";

export type BackendLifecycleState =
  | "stopped"
  | "starting"
  | "running"
  | "stopping"
  | "reconnecting"
  | "error"
  | "crashed";

export type PlaybackState =
  | "idle"
  | "loading"
  | "playing"
  | "buffering"
  | "recovering"
  | "degraded"
  | "failed";

export type StreamProtocol = "webrtc" | "hls";

export type StreamCommandState =
  | "idle"
  | "starting"
  | "restarting"
  | "stopping"
  | "refreshing"
  | "deleting";

export interface ApiResponse<T> {
  status: ApiStatus;
  message: string;
  data: T | null;
  error_code: string | null;
  timestamp: string;
  meta: Record<string, unknown> | null;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface PaginatedItems<T> {
  items: T[];
  pagination: PaginationMeta;
}

export interface CameraResponse {
  id: string;
  name: string;
  location: string | null;
  host: string | null;
  port: number | null;
  path: string | null;
  source_mode: string;
  rtsp_url_preview: string;
  transport: "tcp" | "udp";
  status: "active" | "inactive" | "error";
  stream_status: BackendLifecycleState | null;
  has_credentials: boolean;
  metadata: Record<string, unknown>;
  tags: string[];
  last_validated_at: string | null;
  last_validation_status: "unknown" | "reachable" | "unreachable";
  last_validation_message: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateCameraRequest {
  name: string;
  location?: string | null;
  host?: string | null;
  port: number;
  username?: string | null;
  password?: string | null;
  path?: string | null;
  direct_rtsp_url?: string | null;
  transport: "tcp" | "udp";
  status: "active" | "inactive" | "error";
  metadata: Record<string, unknown>;
  tags: string[];
}

export interface WorkerStateResponse {
  desired_state: "running" | "stopped";
  is_registered: boolean;
  is_process_alive: boolean;
  process_id: number | null;
  restart_count: number;
  reconnect_attempts: number;
  sampled_frames: number;
  dropped_frames: number;
  current_fps: number;
  queue_latency_ms: number;
  decode_time_ms: number;
}

export interface StreamFallbackInfo {
  kind: string;
  message: string;
  retry_after_seconds: number | null;
}

export interface StreamAccessUrls {
  webrtc_url: string;
  hls_url: string;
  rtsp_pull_url: string;
}

export interface StreamInfoResponse {
  camera_id: string;
  camera_name: string;
  stream_id: string;
  stream_name: string;
  stream_identifier: string;
  status: BackendLifecycleState;
  protocol: StreamProtocol;
  playback_url: string | null;
  relative_playback_url: string | null;
  access_urls: StreamAccessUrls;
  websocket_url: string;
  fallback: StreamFallbackInfo | null;
  started_at: string | null;
  updated_at: string | null;
  last_event_at: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  worker: WorkerStateResponse;
}

export interface WebSocketEnvelope {
  type: string;
  topic: string;
  message: string;
  camera_id: string | null;
  data: Record<string, unknown> | null;
  timestamp: string;
}

export interface StartStreamRequest {
  force_restart?: boolean;
  requested_protocol?: StreamProtocol;
  sample_fps?: number;
  enable_tracking_events?: boolean;
  reason?: string;
}

export interface StopStreamRequest {
  reason?: string;
}

export interface PlaybackSnapshot {
  playbackState: PlaybackState;
  playbackProtocol: StreamProtocol | null;
  playbackMessage: string | null;
  playbackError: string | null;
}

export interface StreamTimelineEvent {
  id: string;
  type: string;
  topic: string;
  message: string;
  timestamp: string;
}
