export interface HealthComponent {
  status: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface HealthResponse {
  service: string;
  environment: string;
  version: string;
  uptime_seconds: number;
  components: Record<string, HealthComponent>;
}

export interface StreamHealthResponse {
  healthy: boolean;
  last_error?: string | null;
  connected?: boolean;
  topics?: string[] | null;
  consumed_messages?: number | null;
}

