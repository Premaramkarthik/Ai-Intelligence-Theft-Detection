"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getApiBaseUrl, endpoints } from "@/services/endpoints";

export type WebRTCStreamState =
  | "idle"
  | "connecting"
  | "connected"
  | "retrying"
  | "failed"
  | "closed";

export interface UseWebRTCStreamResult {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  state: WebRTCStreamState;
  attempt: number;
  maxAttempts: number;
  restart: () => void;
}

const STUN_SERVERS: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];

// Mirrors retry.py: wait_exponential(multiplier=BASE_MS, min=BASE_MS, max=MAX_MS)
const MAX_ATTEMPTS = 4; // 1 initial + 3 auto-retries
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 8_000;

function backoffDelay(attempt: number): number {
  // attempt is 1-indexed: attempt 1 → 1s, 2 → 2s, 3 → 4s, 4 → 8s
  return Math.min(MAX_DELAY_MS, BASE_DELAY_MS * Math.pow(2, attempt - 1));
}

export function useWebRTCStream(cameraId: string): UseWebRTCStreamResult {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [state, setState] = useState<WebRTCStreamState>("idle");
  const [attempt, setAttempt] = useState(0);
  // Incrementing restartKey forces the effect to re-run and reconnect from attempt 0.
  const [restartKey, setRestartKey] = useState(0);

  const closePc = useCallback(() => {
    const pc = pcRef.current;
    if (!pc) return;
    pc.onconnectionstatechange = null;
    pc.ontrack = null;
    pc.onicegatheringstatechange = null;
    pc.close();
    pcRef.current = null;
  }, []);

  const connect = useCallback(
    async (attemptNumber: number, signal: AbortSignal): Promise<boolean> => {
      closePc();

      const pc = new RTCPeerConnection({ iceServers: STUN_SERVERS });
      pcRef.current = pc;

      pc.ontrack = (event) => {
        if (signal.aborted) return;
        const [stream] = event.streams;
        if (videoRef.current && stream) {
          videoRef.current.srcObject = stream;
        }
      };

      // Trickle-ICE disabled: wait for full gathering so a single HTTP
      // round-trip completes the handshake.
      pc.addTransceiver("video", { direction: "recvonly" });
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      await new Promise<void>((resolve) => {
        if (pc.iceGatheringState === "complete") { resolve(); return; }
        pc.onicegatheringstatechange = () => {
          if (pc.iceGatheringState === "complete") resolve();
        };
      });

      if (signal.aborted) { pc.close(); return false; }

      const url = `${getApiBaseUrl()}${endpoints.webrtc.offer(cameraId)}`;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sdp: pc.localDescription!.sdp, type: pc.localDescription!.type }),
        signal,
      });

      if (!response.ok) return false;

      const answer = (await response.json()) as { sdp: string; type: RTCSdpType };
      await pc.setRemoteDescription(new RTCSessionDescription(answer));

      // Wait for PC to reach connected or fail.
      const connected = await new Promise<boolean>((resolve) => {
        const check = () => {
          if (signal.aborted) { resolve(false); return; }
          const s = pc.connectionState;
          if (s === "connected") { resolve(true); return; }
          if (s === "failed" || s === "closed" || s === "disconnected") { resolve(false); return; }
        };
        pc.onconnectionstatechange = check;
        check();
      });

      return connected;
    },
    [cameraId, closePc],
  );

  const restart = useCallback(() => {
    setRestartKey((k) => k + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    (async () => {
      for (let i = 1; i <= MAX_ATTEMPTS; i++) {
        if (cancelled || controller.signal.aborted) break;

        setAttempt(i);
        setState(i === 1 ? "connecting" : "retrying");

        let success = false;
        try {
          success = await connect(i, controller.signal);
        } catch {
          success = false;
        }

        if (controller.signal.aborted || cancelled) break;

        if (success) {
          setState("connected");
          return;
        }

        if (i < MAX_ATTEMPTS) {
          const delay = backoffDelay(i);
          console.warn(
            `[WebRTC] ${cameraId} attempt ${i}/${MAX_ATTEMPTS} failed. Retrying in ${delay}ms.`,
          );
          await new Promise((r) => setTimeout(r, delay));
        }
      }

      if (!controller.signal.aborted && !cancelled) {
        setState("failed");
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
      closePc();
      if (videoRef.current) {
        // eslint-disable-next-line react-hooks/exhaustive-deps
        videoRef.current.srcObject = null;
      }
      setState("idle");
      setAttempt(0);
    };
  }, [cameraId, connect, closePc, restartKey]);

  return { videoRef, state, attempt, maxAttempts: MAX_ATTEMPTS, restart };
}
