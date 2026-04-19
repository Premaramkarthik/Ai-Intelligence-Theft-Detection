export interface CameraFrameEvent {
  event: "camera.frame";
  emitted_at: string;
  camera_id: string;
  stream_name: string;
  sequence_number: number;
  captured_at: string;
  width: number;
  height: number;
  pipeline_latency_ms: number;
  motion: {
    mean_magnitude: number;
    dominant_dx: number;
    dominant_dy: number;
    foreground_ratio: number;
    is_motion_consistent: boolean;
  };
  detections: number;
  active_tracks: number;
}

export interface TrackingTrack {
  track_id: string;
  persistent_id: string | null;
  class_name: string | null;
  confidence: number;
  similarity: number | null;
  left: number;
  top: number;
  width: number;
  height: number;
  sampled_at: string;
  age_frames: number;
  consecutive_hits: number;
  frames_since_update: number;
  persistent_id_state: string;
}

export interface TrackingEvent {
  event: "tracking.updated";
  emitted_at: string;
  camera_id: string;
  stream_name: string;
  annotated_stream_name: string;
  active_tracks: number;
  tracks: TrackingTrack[];
}

export interface InferenceEvent {
  event: "inference.updated";
  emitted_at: string;
  camera_id: string;
  stream_name: string;
  persistent_id: string;
  local_track_id: string;
  strategy: "vjepa_probe" | "cnn_transformer" | string;
  score: number;
  alert_level: "normal" | "warning" | "alert" | string;
  label: string;
  model_name: string;
  sampled_at: string;
}

export interface IdentityEvent {
  event: string;
  occurred_at: string;
  camera_id: string;
  stream_name: string;
  local_track_id: string;
  persistent_id: string;
  previous_persistent_id?: string | null;
  matched_existing: boolean;
  similarity?: number | null;
  left: number;
  top: number;
  width: number;
  height: number;
  world_x?: number | null;
  world_y?: number | null;
}

export interface WebSocketEnvelope<TData = Record<string, unknown>> {
  type: string;
  topic: string;
  message: string;
  camera_id?: string | null;
  data?: TData | null;
  timestamp: string;
}

export type RealtimeConnectionState =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "error";

export interface CameraRealtimeSnapshot {
  frame: CameraFrameEvent | null;
  tracking: TrackingEvent | null;
  inference: InferenceEvent[];
  identity: IdentityEvent[];
  lastUpdatedAt: string | null;
}

export interface RealtimeActivityItem {
  id: string;
  cameraId: string | null;
  topic: string;
  label: string;
  tone: "neutral" | "positive" | "warning" | "critical";
  timestamp: string;
}

export interface RealtimeOverviewSnapshot {
  connectionState: RealtimeConnectionState;
  reconnectAttempt: number;
  lastMessageAt: string | null;
  recentActivity: RealtimeActivityItem[];
  streamIds: string[];
}

