'use client';

import { useEffect, useRef, useState } from 'react';

import { buildApiUrl, withApiCredentials } from '@/lib/api';
import type { WebRTCAnswerResponse, WebRTCConfigResponse } from '@/types/contracts';

type WebRTCState = 'idle' | 'connecting' | 'live' | 'fallback' | 'error';
const WEBRTC_ENABLED = process.env.NEXT_PUBLIC_ENABLE_WEBRTC !== 'false';
const CONNECT_TIMEOUT_MS = 5000;
const STALL_POLL_MS = 1500;

interface UseCameraWebRTCReturn {
  mode: 'webrtc' | 'mjpeg';
  state: WebRTCState;
  error: string | null;
  mediaLive: boolean;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}

export function useCameraWebRTC(cameraId: string, enabled: boolean): UseCameraWebRTCReturn {
  const videoRef = useRef<HTMLVideoElement>(null);
  const stateRef = useRef<WebRTCState>('idle');
  const [mode, setMode] = useState<'webrtc' | 'mjpeg'>('mjpeg');
  const [state, setState] = useState<WebRTCState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [mediaLive, setMediaLive] = useState(false);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    if (!enabled || !WEBRTC_ENABLED || typeof window === 'undefined' || typeof RTCPeerConnection === 'undefined') {
      setMode('mjpeg');
      setState('fallback');
      setMediaLive(false);
      return;
    }

    let closed = false;
    let sessionId: string | null = null;
    let peer: RTCPeerConnection | null = null;
    let connectTimeout: ReturnType<typeof setTimeout> | null = null;
    let stallTimer: ReturnType<typeof setInterval> | null = null;
    let lastVideoTime = 0;

    function enterFallback(message?: string) {
      if (message) {
        setError(message);
      }
      setMode('mjpeg');
      setState('fallback');
      setMediaLive(false);
    }

    function clearTimers() {
      if (connectTimeout) {
        clearTimeout(connectTimeout);
        connectTimeout = null;
      }
      if (stallTimer) {
        clearInterval(stallTimer);
        stallTimer = null;
      }
    }

    async function fallbackAndCleanup(message?: string) {
      enterFallback(message);
      await cleanup();
    }

    function startPlaybackWatchdog() {
      if (stallTimer) {
        clearInterval(stallTimer);
      }
      lastVideoTime = videoRef.current?.currentTime ?? 0;
      stallTimer = setInterval(() => {
        const video = videoRef.current;
        if (!video || closed || stateRef.current !== 'live') {
          return;
        }
        const currentTime = video.currentTime;
        if (!video.paused && currentTime > lastVideoTime) {
          lastVideoTime = currentTime;
          setMediaLive(true);
          return;
        }
        void fallbackAndCleanup('WebRTC stream stalled');
      }, STALL_POLL_MS);
    }

    async function cleanup() {
      clearTimers();
      const currentPeer = peer;
      peer = null;
      if (currentPeer) {
        currentPeer.ontrack = null;
        currentPeer.oniceconnectionstatechange = null;
        currentPeer.onconnectionstatechange = null;
        currentPeer.close();
      }
      if (sessionId) {
        try {
          await fetch(buildApiUrl(`/api/camera/${cameraId}/webrtc/session/${sessionId}`), {
            ...withApiCredentials(),
            method: 'DELETE',
          });
        } catch {
          // Best-effort session cleanup for fallback transport.
        }
      }
      sessionId = null;
    }

    async function connect() {
      setState('connecting');
      setError(null);
      setMediaLive(false);
      connectTimeout = setTimeout(() => {
        void fallbackAndCleanup('WebRTC startup timeout');
      }, CONNECT_TIMEOUT_MS);

      try {
        const configResponse = await fetch(buildApiUrl(`/api/camera/${cameraId}/webrtc/config`), {
          ...withApiCredentials(),
        });
        if (!configResponse.ok) {
          throw new Error(`WebRTC config unavailable (${configResponse.status})`);
        }
        const config = (await configResponse.json()) as WebRTCConfigResponse;
        peer = new RTCPeerConnection({
          iceServers: config.ice_servers.map((server) => ({
            urls: server.urls,
            username: server.username ?? undefined,
            credential: server.credential ?? undefined,
          })),
        });
        peer.addTransceiver('video', { direction: 'recvonly' });

        peer.ontrack = (event) => {
          const [stream] = event.streams;
          if (videoRef.current && stream) {
            videoRef.current.srcObject = stream;
            void videoRef.current.play().catch(() => undefined);
          }
          if (connectTimeout) {
            clearTimeout(connectTimeout);
            connectTimeout = null;
          }
          setMode('webrtc');
          setState('live');
          startPlaybackWatchdog();
        };

        peer.onconnectionstatechange = () => {
          if (!peer || closed) {
            return;
          }
          if (peer.connectionState === 'failed' || peer.connectionState === 'disconnected') {
            void fallbackAndCleanup(`WebRTC ${peer.connectionState}`);
          }
        };

        const offer = await peer.createOffer();
        await peer.setLocalDescription(offer);

        const response = await fetch(buildApiUrl(`/api/camera/${cameraId}/webrtc/offer`), {
          ...withApiCredentials(),
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sdp: offer.sdp,
            type: offer.type,
          }),
        });

        if (!response.ok) {
          throw new Error(`WebRTC unavailable (${response.status})`);
        }

        const payload = (await response.json()) as WebRTCAnswerResponse;
        sessionId = payload.session_id;
        await peer.setRemoteDescription({ type: payload.type, sdp: payload.sdp });
      } catch (err) {
        await fallbackAndCleanup(err instanceof Error ? err.message : 'WebRTC unavailable');
      }
    }

    void connect();

    return () => {
      closed = true;
      void cleanup();
    };
  }, [cameraId, enabled]);

  return {
    mode,
    state,
    error,
    mediaLive,
    videoRef,
  };
}
