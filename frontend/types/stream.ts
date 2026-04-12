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
export type PlaybackViewMode = "raw" | "tracked";

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

export interface TrackingTrackResponse {
  track_id: string;
  persistent_id: string | null;
  class_name: string | null;
  confidence: number;
  similarity: number | null;
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface TrackingStateResponse {
  enabled: boolean;
  stream_name: string | null;
  access_urls: StreamAccessUrls | null;
  is_registered: boolean;
  is_process_alive: boolean;
  reconnect_attempts: number;
  active_tracks: number;
  identity_backend: string;
  last_error_message: string | null;
  tracks: TrackingTrackResponse[];
}

export interface TrackingUpdateEnvelopeData {
  stream_name?: string | null;
  annotated_stream_name?: string | null;
  active_tracks?: number;
  tracks?: TrackingTrackResponse[];
}

export type InferenceAlertLevel = "normal" | "warning" | "alert";

export interface InferenceStateResponse {
  enabled: boolean;
  strategy: string | null;
  available_strategies: string[];
  healthy: boolean;
  last_error_message: string | null;
  queue_depth: number;
  active_tracks: number;
  last_result_at: string | null;
}

export interface InferenceEvent {
  camera_id: string;
  stream_name: string;
  persistent_id: string;
  local_track_id: string;
  strategy: string;
  score: number;
  alert_level: InferenceAlertLevel;
  label: string;
  model_name: string;
  sampled_at: string;
  emitted_at: string;
}

export interface InferenceAlertEnvelopeData {
  alert_level: InferenceAlertLevel;
  persistent_id: string;
  camera_id: string;
  score: number;
  strategy: string;
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
  tracking: TrackingStateResponse | null;
  inference: InferenceStateResponse | null;
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
  enable_inference?: boolean;
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

