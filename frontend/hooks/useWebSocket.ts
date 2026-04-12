"use client";

import { useEffect, useEffectEvent, useMemo } from "react";

import { buildStreamUpdatesWebSocketUrl, parseWebSocketEnvelope } from "@/lib/websocket";
import { useStreamStore } from "@/store/streamStore";

const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000, 8_000];
const HEARTBEAT_INTERVAL_MS = 25_000;

export function useWebSocket(
  cameraId?: string,
  rawWebSocketUrl?: string | null,
  enabled = true,
): void {
  const applyWebSocketEnvelope = useStreamStore(
    (state) => state.applyWebSocketEnvelope,
  );

  const handleMessage = useEffectEvent((event: MessageEvent<string>) => {
    const envelope = parseWebSocketEnvelope(event.data);
    if (!envelope) {
      return;
    }
    applyWebSocketEnvelope(envelope);
  });

  const websocketUrl = useMemo(
    () => buildStreamUpdatesWebSocketUrl(cameraId, rawWebSocketUrl),
    [cameraId, rawWebSocketUrl],
  );

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let heartbeatTimer: number | null = null;
    let reconnectAttempt = 0;
    let disposed = false;

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const clearHeartbeatTimer = () => {
      if (heartbeatTimer !== null) {
        window.clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
    };

    const scheduleReconnect = () => {
      if (disposed || reconnectTimer !== null) {
        return;
      }

      const delay =
        RECONNECT_DELAYS_MS[
          Math.min(reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)
        ];
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    };

    const connect = () => {
      clearReconnectTimer();
      clearHeartbeatTimer();
      socket = new WebSocket(websocketUrl);

      socket.addEventListener("open", () => {
        if (disposed) {
          socket?.close();
          return;
        }
        reconnectAttempt = 0;
        heartbeatTimer = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send("ping");
          }
        }, HEARTBEAT_INTERVAL_MS);
      });

      socket.addEventListener("message", handleMessage);

      socket.addEventListener("error", () => {
        if (socket && socket.readyState < WebSocket.CLOSING) {
          socket.close();
        }
      });

      socket.addEventListener("close", () => {
        clearHeartbeatTimer();
        if (disposed) {
          return;
        }
        scheduleReconnect();
      });
    };

    connect();

    return () => {
      disposed = true;
      clearReconnectTimer();
      clearHeartbeatTimer();
      if (socket?.readyState !== undefined && socket.readyState < WebSocket.CLOSING) {
        socket.close();
      }
    };
  }, [enabled, websocketUrl]);
}
