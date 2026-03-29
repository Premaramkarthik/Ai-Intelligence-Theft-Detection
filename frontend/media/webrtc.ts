"use client";

import type { StreamProtocol } from "@/types/stream";

export type MediaAdapterEventType =
  | "connected"
  | "failed"
  | "disconnected"
  | "stalled";

export interface MediaAdapterEvent {
  type: MediaAdapterEventType;
  protocol: StreamProtocol;
  message: string;
  error?: string;
}

type MediaAdapterListener = (event: MediaAdapterEvent) => void;

const CONNECT_TIMEOUT_MS = 8_000;
const STALL_THRESHOLD_MS = 4_000;

export class WebRtcAdapter {
  private readonly listeners = new Set<MediaAdapterListener>();

  private peerConnection: RTCPeerConnection | null = null;

  private sessionUrl: string | null = null;

  private videoElement: HTMLVideoElement | null = null;

  private abortController: AbortController | null = null;

  private stallIntervalId: number | null = null;

  private lastProgressTimestamp = 0;

  private hasPlaybackProgress = false;

  private connected = false;

  private readonly onVideoProgress = () => {
    this.hasPlaybackProgress = true;
    this.lastProgressTimestamp = Date.now();
  };

  subscribe(listener: MediaAdapterListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async start(videoElement: HTMLVideoElement, whepUrl: string): Promise<void> {
    await this.stop();
    this.connected = false;
    this.hasPlaybackProgress = false;
    this.videoElement = videoElement;
    this.abortController = new AbortController();
    this.attachVideoListeners(videoElement);

    const peerConnection = new RTCPeerConnection();
    this.peerConnection = peerConnection;

    const remoteStream = new MediaStream();
    videoElement.srcObject = remoteStream;
    videoElement.muted = true;
    videoElement.playsInline = true;

    peerConnection.addEventListener("track", (event) => {
      event.streams.forEach((stream) => {
        stream.getTracks().forEach((track) => remoteStream.addTrack(track));
      });
      void videoElement.play().catch(() => undefined);
      this.emit({
        type: "connected",
        protocol: "webrtc",
        message: "WebRTC playback connected.",
      });
      this.connected = true;
    });

    peerConnection.addEventListener("connectionstatechange", () => {
      if (peerConnection.connectionState === "connected") {
        this.lastProgressTimestamp = Date.now();
        if (!this.connected) {
          this.connected = true;
          this.emit({
            type: "connected",
            protocol: "webrtc",
            message: "WebRTC playback connected.",
          });
        }
        return;
      }

      if (peerConnection.connectionState === "disconnected") {
        this.emit({
          type: "disconnected",
          protocol: "webrtc",
          message: "WebRTC playback disconnected.",
        });
        return;
      }

      if (peerConnection.connectionState === "failed") {
        this.emit({
          type: "failed",
          protocol: "webrtc",
          message: "WebRTC playback failed.",
        });
      }
    });

    peerConnection.addTransceiver("video", { direction: "recvonly" });

    try {
      const offer = await peerConnection.createOffer();
      await peerConnection.setLocalDescription(offer);
      await waitForIceGathering(peerConnection);

      const response = await fetch(whepUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/sdp",
        },
        body: peerConnection.localDescription?.sdp,
        signal: this.abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`WHEP handshake failed with ${response.status}.`);
      }

      const location = response.headers.get("Location");
      if (location) {
        this.sessionUrl = new URL(location, whepUrl).toString();
      }

      const answerSdp = await response.text();
      await peerConnection.setRemoteDescription({
        type: "answer",
        sdp: answerSdp,
      });

      this.startStallMonitor(videoElement);
      await this.waitForConnection();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown WebRTC failure.";
      this.emit({
        type: "failed",
        protocol: "webrtc",
        message: "WebRTC playback setup failed.",
        error: message,
      });
      await this.stop();
      throw error;
    }
  }

  async stop(): Promise<void> {
    if (this.stallIntervalId !== null) {
      window.clearInterval(this.stallIntervalId);
      this.stallIntervalId = null;
    }

    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }

    if (this.peerConnection) {
      this.peerConnection.ontrack = null;
      this.peerConnection.close();
      this.peerConnection = null;
    }

    if (this.videoElement) {
      this.detachVideoListeners(this.videoElement);
      this.videoElement.pause();
      this.videoElement.srcObject = null;
    }

    if (this.sessionUrl) {
      const sessionUrl = this.sessionUrl;
      this.sessionUrl = null;
      void fetch(sessionUrl, { method: "DELETE" }).catch(() => undefined);
    }

    this.connected = false;
    this.hasPlaybackProgress = false;
  }

  private emit(event: MediaAdapterEvent): void {
    this.listeners.forEach((listener) => listener(event));
  }

  private attachVideoListeners(videoElement: HTMLVideoElement): void {
    videoElement.addEventListener("playing", this.onVideoProgress);
    videoElement.addEventListener("timeupdate", this.onVideoProgress);
    videoElement.addEventListener("waiting", this.onVideoWaiting);
    videoElement.addEventListener("stalled", this.onVideoWaiting);
  }

  private detachVideoListeners(videoElement: HTMLVideoElement): void {
    videoElement.removeEventListener("playing", this.onVideoProgress);
    videoElement.removeEventListener("timeupdate", this.onVideoProgress);
    videoElement.removeEventListener("waiting", this.onVideoWaiting);
    videoElement.removeEventListener("stalled", this.onVideoWaiting);
  }

  private readonly onVideoWaiting = () => {
    if (!this.connected || !this.hasPlaybackProgress) {
      return;
    }
    this.emit({
      type: "stalled",
      protocol: "webrtc",
      message: "WebRTC playback stalled.",
    });
  };

  private startStallMonitor(videoElement: HTMLVideoElement): void {
    this.lastProgressTimestamp = Date.now();
    this.stallIntervalId = window.setInterval(() => {
      if (
        document.hidden ||
        videoElement.paused ||
        videoElement.ended ||
        !this.connected ||
        !this.hasPlaybackProgress
      ) {
        return;
      }

      if (Date.now() - this.lastProgressTimestamp >= STALL_THRESHOLD_MS) {
        this.emit({
          type: "stalled",
          protocol: "webrtc",
          message: "WebRTC playback stopped progressing.",
        });
      }
    }, 2_000);
  }

  private waitForConnection(): Promise<void> {
    if (this.connected) {
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        unsubscribe();
        reject(new Error("WebRTC connection timed out."));
      }, CONNECT_TIMEOUT_MS);

      const unsubscribe = this.subscribe((event) => {
        if (event.type === "connected") {
          window.clearTimeout(timeoutId);
          unsubscribe();
          resolve();
        }

        if (event.type === "failed" || event.type === "disconnected") {
          window.clearTimeout(timeoutId);
          unsubscribe();
          reject(new Error(event.error ?? event.message));
        }
      });
    });
  }
}

async function waitForIceGathering(
  peerConnection: RTCPeerConnection,
): Promise<void> {
  if (peerConnection.iceGatheringState === "complete") {
    return;
  }

  await new Promise<void>((resolve) => {
    const onStateChange = () => {
      if (peerConnection.iceGatheringState === "complete") {
        peerConnection.removeEventListener(
          "icegatheringstatechange",
          onStateChange,
        );
        resolve();
      }
    };

    peerConnection.addEventListener("icegatheringstatechange", onStateChange);
  });
}
