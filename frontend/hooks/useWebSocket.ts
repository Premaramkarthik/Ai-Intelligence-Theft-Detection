"use client";

import { useEffect, useEffectEvent, useMemo } from "react";

import { buildStreamUpdatesWebSocketUrl, parseWebSocketEnvelope } from "@/lib/websocket";
import { useStreamStore } from "@/store/streamStore";

const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000, 8_000];

export function useWebSocket(
  cameraId?: string,
  rawWebSocketUrl?: string | null,
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
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempt = 0;
    let disposed = false;

    const connect = () => {
      socket = new WebSocket(websocketUrl);

      socket.addEventListener("open", () => {
        if (disposed) {
          socket?.close();
          return;
        }
        reconnectAttempt = 0;
      });

      socket.addEventListener("message", handleMessage);

      socket.addEventListener("close", () => {
        if (disposed) {
          return;
        }

        const delay =
          RECONNECT_DELAYS_MS[
            Math.min(reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)
          ];
        reconnectAttempt += 1;
        reconnectTimer = window.setTimeout(connect, delay);
      });
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      if (socket?.readyState === WebSocket.OPEN) {
        socket.close();
      }
    };
  }, [websocketUrl]);
}
