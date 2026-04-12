"use client";

import { HlsAdapter } from "@/media/hls";
import type { MediaAdapterEvent } from "@/media/webrtc";
import { WebRtcAdapter } from "@/media/webrtc";
import type { PlaybackSnapshot } from "@/types/stream";

const RETRY_DELAYS_MS = [0, 1_000, 2_000, 4_000, 8_000];

interface StreamSources {
  webrtcUrl: string;
  hlsUrl: string;
}

interface StreamOrchestratorOptions {
  maxRetries?: number;
  onPlaybackSnapshot: (snapshot: PlaybackSnapshot) => void;
}

export class StreamOrchestrator {
  private readonly webRtcAdapter = new WebRtcAdapter();

  private readonly hlsAdapter = new HlsAdapter();

  private readonly maxRetries: number;

  private readonly onPlaybackSnapshot: (snapshot: PlaybackSnapshot) => void;

  private videoElement: HTMLVideoElement | null = null;

  private sources: StreamSources | null = null;

  private retryCount = 0;

  private startToken = 0;

  private retryTimerId: number | null = null;

  private stopRequested = true;

  private unsubscribeWebRtc: (() => void) | null = null;

  private unsubscribeHls: (() => void) | null = null;

  constructor(options: StreamOrchestratorOptions) {
    this.maxRetries = options.maxRetries ?? 5;
    this.onPlaybackSnapshot = options.onPlaybackSnapshot;
  }

  attach(videoElement: HTMLVideoElement): void {
    this.videoElement = videoElement;
  }

  setSources(sources: StreamSources): void {
    this.sources = sources;
  }

  async start(): Promise<void> {
    if (!this.videoElement || !this.sources) {
      return;
    }

    this.stopRequested = false;
    this.startToken += 1;
    this.retryCount = 0;
    if (this.retryTimerId !== null) {
      window.clearTimeout(this.retryTimerId);
      this.retryTimerId = null;
    }
    await this.clearAdapters();
    await this.activateWebRtc(this.startToken, 0);
  }

  async reconnect(): Promise<void> {
    await this.start();
  }

  async stop(): Promise<void> {
    this.stopRequested = true;
    this.startToken += 1;
    if (this.retryTimerId !== null) {
      window.clearTimeout(this.retryTimerId);
      this.retryTimerId = null;
    }
    await this.clearAdapters();
    this.onPlaybackSnapshot({
      playbackState: "idle",
      playbackProtocol: null,
      playbackMessage: null,
      playbackError: null,
    });
  }

  private async activateWebRtc(token: number, attempt: number): Promise<void> {
    if (!this.videoElement || !this.sources || this.stopRequested) {
      return;
    }

    this.retryCount = attempt;
    this.unsubscribeWebRtc?.();
    this.unsubscribeWebRtc = this.webRtcAdapter.subscribe((event) => {
      void this.handleWebRtcEvent(token, event);
    });

    this.onPlaybackSnapshot({
      playbackState: attempt === 0 ? "loading" : "recovering",
      playbackProtocol: "webrtc",
      playbackMessage:
        attempt === 0
          ? "Starting low-latency WebRTC playback."
          : `Recovering WebRTC playback (attempt ${attempt} of ${this.maxRetries}).`,
      playbackError: null,
    });

    try {
      await this.webRtcAdapter.start(this.videoElement, this.sources.webrtcUrl);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "WebRTC startup failed.";
      await this.scheduleWebRtcRetry(token, message);
    }
  }

  private async handleWebRtcEvent(
    token: number,
    event: MediaAdapterEvent,
  ): Promise<void> {
    if (token !== this.startToken || this.stopRequested) {
      return;
    }

    if (event.type === "connected") {
      this.onPlaybackSnapshot({
        playbackState: "playing",
        playbackProtocol: "webrtc",
        playbackMessage: event.message,
        playbackError: null,
      });
      return;
    }

    if (event.type === "stalled") {
      this.onPlaybackSnapshot({
        playbackState: "buffering",
        playbackProtocol: "webrtc",
        playbackMessage: event.message,
        playbackError: null,
      });
      await this.scheduleWebRtcRetry(token, event.message);
      return;
    }

    await this.scheduleWebRtcRetry(token, event.error ?? event.message);
  }

  private async scheduleWebRtcRetry(
    token: number,
    reason: string,
  ): Promise<void> {
    if (token !== this.startToken || this.stopRequested) {
      return;
    }

    await this.webRtcAdapter.stop();
    if (this.retryTimerId !== null) {
      window.clearTimeout(this.retryTimerId);
      this.retryTimerId = null;
    }

    const nextAttempt = this.retryCount + 1;
    if (nextAttempt >= this.maxRetries) {
      await this.activateHlsFallback(token, reason);
      return;
    }

    const delay = RETRY_DELAYS_MS[Math.min(nextAttempt - 1, RETRY_DELAYS_MS.length - 1)];
    this.onPlaybackSnapshot({
      playbackState: "recovering",
      playbackProtocol: "webrtc",
      playbackMessage:
        delay === 0
          ? "Retrying WebRTC immediately."
          : `Retrying WebRTC in ${delay / 1000}s.`,
      playbackError: reason,
    });

    this.retryTimerId = window.setTimeout(() => {
      this.retryTimerId = null;
      void this.activateWebRtc(token, nextAttempt);
    }, delay);
  }

  private async activateHlsFallback(
    token: number,
    reason: string,
  ): Promise<void> {
    if (!this.videoElement || !this.sources || this.stopRequested) {
      return;
    }

    this.unsubscribeHls?.();
    this.unsubscribeHls = this.hlsAdapter.subscribe((event) => {
      if (token !== this.startToken || this.stopRequested) {
        return;
      }

      if (event.type === "connected") {
        this.onPlaybackSnapshot({
          playbackState: "degraded",
          playbackProtocol: "hls",
          playbackMessage: "WebRTC unavailable. Showing HLS fallback.",
          playbackError: reason,
        });
        return;
      }

      if (event.type === "stalled") {
        this.onPlaybackSnapshot({
          playbackState: "buffering",
          playbackProtocol: "hls",
          playbackMessage: event.message,
          playbackError: reason,
        });
        return;
      }

      this.onPlaybackSnapshot({
        playbackState: "failed",
        playbackProtocol: "hls",
        playbackMessage: "HLS fallback failed.",
        playbackError: event.error ?? event.message,
      });
    });

    this.onPlaybackSnapshot({
      playbackState: "degraded",
      playbackProtocol: "hls",
      playbackMessage: "Switching to HLS fallback.",
      playbackError: reason,
    });

    try {
      await this.hlsAdapter.start(this.videoElement, this.sources.hlsUrl);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "HLS fallback failed.";
      this.onPlaybackSnapshot({
        playbackState: "failed",
        playbackProtocol: "hls",
        playbackMessage: "HLS fallback failed.",
        playbackError: message,
      });
    }
  }

  private async clearAdapters(): Promise<void> {
    if (this.retryTimerId !== null) {
      window.clearTimeout(this.retryTimerId);
      this.retryTimerId = null;
    }
    this.unsubscribeWebRtc?.();
    this.unsubscribeWebRtc = null;
    this.unsubscribeHls?.();
    this.unsubscribeHls = null;
    await this.webRtcAdapter.stop();
    await this.hlsAdapter.stop();
  }
}
