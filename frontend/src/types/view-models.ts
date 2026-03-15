export interface Camera {
  id: string;
  name: string;
  url: string;
  organization_id?: string;
  store_id?: string;
  status: 'online' | 'offline' | 'connecting';
  lastDetection?: string;
}

export interface SystemStatus {
  status: 'healthy' | 'degraded' | 'disconnected' | 'loading';
  gpu_util: number;
  gpu_mem: number;
  gpu_temp: number;
  cpu_usage: number;
  ram_usage: number;
  connection: 'connected' | 'reconnecting' | 'disconnected';
}
