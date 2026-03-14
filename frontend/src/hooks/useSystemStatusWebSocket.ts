'use client';

import { useEffect } from 'react';

import { buildWsUrl } from '@/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';
import { useCameraStore } from '@/stores/useCameraStore';

export function useSystemStatusWebSocket() {
  const token = useAuthStore((state) => state.token);
  const setSystemStatus = useCameraStore((state) => state.setSystemStatus);

  useEffect(() => {
    if (!token) {
      return;
    }

    const socket = new WebSocket(buildWsUrl('/ws/status', token));

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setSystemStatus({
          status: 'healthy',
          gpu_util: data.gpu?.utilization ?? 0,
          gpu_mem: data.gpu?.used ?? 0,
          gpu_temp: data.gpu?.temperature ?? 0,
          cpu_usage: data.system?.cpu_usage ?? 0,
          ram_usage: data.system?.ram_usage ?? 0,
        });
      } catch (err) {
        console.error('Failed to parse system status', err);
      }
    };

    socket.onerror = () => {
      setSystemStatus({
        status: 'degraded',
        gpu_util: 0,
        gpu_mem: 0,
        gpu_temp: 0,
        cpu_usage: 0,
        ram_usage: 0,
      });
    };

    return () => socket.close();
  }, [setSystemStatus, token]);
}
