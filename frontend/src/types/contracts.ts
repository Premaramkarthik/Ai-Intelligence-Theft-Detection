export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type ReviewStatus = 'unreviewed' | 'confirmed' | 'false_positive' | 'needs_review';

export interface DetectionPayload {
  bbox: number[];
  label: string;
  confidence: number;
  track_id?: string | number | null;
}

export interface IncidentPayload {
  label: string;
  confidence: number;
  severity: Severity;
}

export interface CameraStreamMessage {
  message_type: 'camera.metadata';
  camera_id: string;
  trace_id?: string | null;
  timestamp?: string | null;
  detections: DetectionPayload[];
  incident: IncidentPayload | null;
  review_status?: ReviewStatus;
  metadata?: Record<string, unknown>;
}

export interface HistoryEvent {
  event_id: string;
  organization_id: string;
  store_id: string;
  camera_id: string;
  trace_id: string;
  timestamp: string;
  label: string;
  confidence: number;
  severity: Severity;
  event_type: string;
  review_status: ReviewStatus;
  review_note?: string | null;
  evidence_uri?: string | null;
  thumbnail_uri?: string | null;
  model_version?: string | null;
  config_version?: string | null;
  detections?: DetectionPayload[];
  metadata?: Record<string, unknown>;
}

export interface ConnectResponse {
  status: string;
  message: string;
  stream_ids: string[];
  organization_id: string;
  store_id: string;
}

export interface TokenResponse {
  authenticated: boolean;
  access_token?: string | null;
  token_type: string;
}

export interface SessionResponse {
  authenticated: boolean;
  username?: string | null;
}

export interface IceServerConfig {
  urls: string[];
  username?: string | null;
  credential?: string | null;
}

export interface WebRTCOfferRequest {
  sdp: string;
  type: 'offer';
}

export interface WebRTCAnswerResponse {
  session_id: string;
  sdp: string;
  type: 'answer';
  ice_servers: IceServerConfig[];
  preview_transport: 'webrtc';
}

export interface WebRTCConfigResponse {
  ice_servers: IceServerConfig[];
  preview_transport: 'webrtc';
}

export type CameraSourcesResponse = Record<string, string>;

export interface GpuStatus {
  available: boolean;
  total?: number | null;
  used?: number | null;
  free?: number | null;
  utilization?: number | null;
  temperature?: number | null;
  error?: string | null;
}

export interface SystemResourceStatus {
  cpu_usage: number;
  ram_usage: number;
}

export interface CameraFleetStatus {
  total_configured: number;
  active_streaming: number;
}

export interface SystemStatusMessage {
  message_type?: 'system.status';
  status: 'healthy' | 'degraded';
  redis?: string | null;
  cameras?: CameraFleetStatus | null;
  gpu?: GpuStatus | null;
  system?: SystemResourceStatus | null;
  uptime?: number | null;
  ts?: number | null;
}
