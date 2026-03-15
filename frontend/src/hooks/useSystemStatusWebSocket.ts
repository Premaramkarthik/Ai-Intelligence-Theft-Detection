'use client';

import { useEffect } from 'react';

import { buildWsUrl } from '@/lib/api';
import { getAuthFailureMessage } from '@/lib/auth';
import { toSystemStatus } from '@/lib/systemStatus';
import { safeDisposeWebSocket } from '@/lib/websocket';
import { useAuthStore } from '@/stores/useAuthStore';
import { useCameraStore } from '@/stores/useCameraStore';
import type { SystemStatusMessage } from '@/types/contracts';

export function useSystemStatusWebSocket() {
  const token = useAuthStore((state) => state.token);
  const logout = useAuthStore((state) => state.logout);
  const setSystemStatus = useCameraStore((state) => state.setSystemStatus);

  useEffect(() => {
    if (!token) {
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempt = 0;
    let closed = false;
    let intentionalClose = false;

    const setDisconnected = (status: 'degraded' | 'disconnected', connection: 'reconnecting' | 'disconnected') => {
      setSystemStatus({
        status,
        gpu_util: 0,
        gpu_mem: 0,
        gpu_temp: 0,
        cpu_usage: 0,
        ram_usage: 0,
        connection,
      });
    };

    const connect = () => {
      if (closed) {
        return;
      }
      intentionalClose = false;
      socket = new WebSocket(buildWsUrl('/ws/status'));

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as SystemStatusMessage;
          reconnectAttempt = 0;
          setSystemStatus(toSystemStatus(data));
        } catch (err) {
          console.error('Failed to parse system status', err);
        }
      };

      socket.onclose = (event) => {
        if (closed || intentionalClose) {
          return;
        }
        if (event.code === 1008) {
          console.warn(getAuthFailureMessage());
          logout();
          return;
        }
        reconnectAttempt += 1;
        setDisconnected(reconnectAttempt > 3 ? 'disconnected' : 'degraded', 'reconnecting');
        reconnectTimer = setTimeout(connect, Math.min(1000 * reconnectAttempt, 5000));
      };

      socket.onerror = () => {
        setDisconnected('degraded', 'reconnecting');
      };
    };

    connect();

    return () => {
      closed = true;
      intentionalClose = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      safeDisposeWebSocket(socket);
    };
  }, [logout, setSystemStatus, token]);
}
