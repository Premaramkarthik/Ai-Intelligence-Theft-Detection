"use client";

import { useEffect, useEffectEvent, useMemo } from "react";

import {
  buildInferenceUpdatesWebSocketUrl,
  parseWebSocketEnvelope,
} from "@/lib/websocket";
import { useStreamStore } from "@/store/streamStore";

const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000, 8_000];
const ACTIVE_EVENT_TTL_MS = 3_000;

export function useInferenceWebSocket(
  enabled: boolean,
  cameraId?: string,
  rawWebSocketUrl?: string | null,
): void {
  const applyInferenceEnvelope = useStreamStore(
    (state) => state.applyInferenceEnvelope,
  );
  const pruneInferenceEvents = useStreamStore((state) => state.pruneInferenceEvents);

  const handleMessage = useEffectEvent((event: MessageEvent<string>) => {
    const envelope = parseWebSocketEnvelope(event.data);
    if (!envelope) {
      return;
    }
    applyInferenceEnvelope(envelope);
  });

  const websocketUrl = useMemo(
    () => buildInferenceUpdatesWebSocketUrl(cameraId, rawWebSocketUrl),
    [cameraId, rawWebSocketUrl],
  );

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempt = 0;
    let disposed = false;
    let pruneTimer: number | null = null;

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
    pruneTimer = window.setInterval(() => {
      pruneInferenceEvents(ACTIVE_EVENT_TTL_MS);
    }, 1_000);

    return () => {
      disposed = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      if (pruneTimer !== null) {
        window.clearInterval(pruneTimer);
      }
      if (socket?.readyState === WebSocket.OPEN) {
        socket.close();
      }
    };
  }, [enabled, pruneInferenceEvents, websocketUrl]);
}
