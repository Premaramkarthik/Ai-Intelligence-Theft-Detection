export interface PaginatedItems<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApiResponse<T> {
  status: "success" | "error";
  message: string;
  data: T | null;
  error_code?: string;
}

export interface CameraResponse {
  id: string;
  name: string;
  location: string | null;
  host: string | null;
  port: number;
  username: string | null;
  path: string | null;
  direct_rtsp_url: string | null;
  transport: "tcp" | "udp";
  rtsp_url_preview: string;
  status: string;
  stream_status?: string;
  tags: string[];
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
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
  transport: "tcp" | "udp";
  status: string;
  tags: string[];
  metadata?: Record<string, unknown>;
}
