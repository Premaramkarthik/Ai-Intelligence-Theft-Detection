"use client";

import Hls from "hls.js";

import type { StreamProtocol } from "@/types/stream";
import type { MediaAdapterEvent, MediaAdapterEventType } from "@/media/webrtc";

type MediaAdapterListener = (event: MediaAdapterEvent) => void;

export class HlsAdapter {
  private readonly listeners = new Set<MediaAdapterListener>();

  private hls: Hls | null = null;

  private videoElement: HTMLVideoElement | null = null;

  subscribe(listener: MediaAdapterListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async start(videoElement: HTMLVideoElement, hlsUrl: string): Promise<void> {
    await this.stop();
    this.videoElement = videoElement;
    videoElement.muted = true;
    videoElement.playsInline = true;
    videoElement.addEventListener("waiting", this.onWaiting);
    videoElement.addEventListener("stalled", this.onWaiting);

    if (Hls.isSupported()) {
      this.hls = new Hls({
        lowLatencyMode: true,
        enableWorker: true,
      });

      this.hls.on(Hls.Events.MEDIA_ATTACHED, () => {
        this.hls?.loadSource(hlsUrl);
      });

      this.hls.on(Hls.Events.MANIFEST_PARSED, () => {
        void videoElement.play().catch(() => undefined);
        this.emit("connected", "HLS fallback connected.");
      });

      this.hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) {
          this.emit("failed", "HLS playback failed.", data.error?.message);
          return;
        }
        this.emit("stalled", "HLS playback stalled.");
      });

      this.hls.attachMedia(videoElement);
      return;
    }

    if (videoElement.canPlayType("application/vnd.apple.mpegurl")) {
      videoElement.src = hlsUrl;
      videoElement.addEventListener("loadedmetadata", this.onNativeLoadedMetadata);
      return;
    }

    this.emit(
      "failed",
      "This browser cannot play HLS fallback streams.",
      "No HLS playback capability detected.",
    );
    throw new Error("HLS is not supported in this browser.");
  }

  async stop(): Promise<void> {
    if (this.hls) {
      this.hls.destroy();
      this.hls = null;
    }

    if (this.videoElement) {
      this.videoElement.removeEventListener("waiting", this.onWaiting);
      this.videoElement.removeEventListener("stalled", this.onWaiting);
      this.videoElement.removeEventListener(
        "loadedmetadata",
        this.onNativeLoadedMetadata,
      );
      this.videoElement.pause();
      this.videoElement.removeAttribute("src");
      this.videoElement.load();
      this.videoElement = null;
    }
  }

  private emit(
    type: MediaAdapterEventType,
    message: string,
    error?: string,
  ): void {
    const event: MediaAdapterEvent = {
      type,
      protocol: "hls" satisfies StreamProtocol,
      message,
      error,
    };
    this.listeners.forEach((listener) => listener(event));
  }

  private readonly onWaiting = () => {
    this.emit("stalled", "HLS playback stalled.");
  };

  private readonly onNativeLoadedMetadata = () => {
    void this.videoElement?.play().catch(() => undefined);
    this.emit("connected", "HLS fallback connected.");
  };
}
