"use client";

import { useEffect, useMemo, useRef } from "react";

import type { InferenceEvent, TrackingTrackResponse } from "@/types/stream";

interface TrackingCanvasOverlayProps {
  enabled: boolean;
  videoElement: HTMLVideoElement | null;
  tracks: TrackingTrackResponse[];
  inferenceEvents?: InferenceEvent[];
}

function getTrackColor(inferenceEvent?: InferenceEvent): string {
  if (inferenceEvent?.alert_level === "alert") {
    return "#fb7185";
  }
  if (inferenceEvent?.alert_level === "warning") {
    return "#fbbf24";
  }
  return "#34d399";
}

function getDisplayRect(
  containerWidth: number,
  containerHeight: number,
  videoWidth: number,
  videoHeight: number,
) {
  const scale = Math.min(containerWidth / videoWidth, containerHeight / videoHeight);
  const width = videoWidth * scale;
  const height = videoHeight * scale;
  return {
    left: (containerWidth - width) / 2,
    top: (containerHeight - height) / 2,
    width,
    height,
  };
}

export function TrackingCanvasOverlay({
  enabled,
  videoElement,
  tracks,
  inferenceEvents = [],
}: TrackingCanvasOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const latestInferenceByKey = useMemo(() => {
    const entries = new Map<string, InferenceEvent>();
    inferenceEvents.forEach((event) => {
      entries.set(event.persistent_id, event);
      entries.set(event.local_track_id, event);
    });
    return entries;
  }, [inferenceEvents]);
  const activeTracks = useMemo(() => {
    return tracks
      .filter((track) => track.width > 0 && track.height > 0)
      .map((track) => ({
        track,
        inferenceEvent:
          (track.persistent_id
            ? latestInferenceByKey.get(track.persistent_id)
            : undefined) ?? latestInferenceByKey.get(track.track_id),
      }));
  }, [latestInferenceByKey, tracks]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return undefined;
    }

    let frameId = 0;

    const render = () => {
      const context = canvas.getContext("2d");
      if (!context) {
        frameId = window.requestAnimationFrame(render);
        return;
      }

      const bounds = canvas.getBoundingClientRect();
      const devicePixelRatio = window.devicePixelRatio || 1;
      const width = Math.max(Math.round(bounds.width * devicePixelRatio), 1);
      const height = Math.max(Math.round(bounds.height * devicePixelRatio), 1);

      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      context.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
      context.clearRect(0, 0, bounds.width, bounds.height);

      if (!enabled || !videoElement || activeTracks.length === 0) {
        frameId = window.requestAnimationFrame(render);
        return;
      }

      const videoWidth = videoElement.videoWidth;
      const videoHeight = videoElement.videoHeight;
      if (!videoWidth || !videoHeight) {
        frameId = window.requestAnimationFrame(render);
        return;
      }

      const displayRect = getDisplayRect(
        bounds.width,
        bounds.height,
        videoWidth,
        videoHeight,
      );

      context.lineWidth = 2.5;
      context.font =
        '600 12px "IBM Plex Sans", "Segoe UI", sans-serif';
      context.textBaseline = "middle";

      activeTracks.forEach(({ track, inferenceEvent }) => {
        const color = getTrackColor(inferenceEvent);
        const left = displayRect.left + (track.left / videoWidth) * displayRect.width;
        const top = displayRect.top + (track.top / videoHeight) * displayRect.height;
        const widthPx = (track.width / videoWidth) * displayRect.width;
        const heightPx = (track.height / videoHeight) * displayRect.height;

        context.strokeStyle = color;
        context.shadowColor = "rgba(2, 6, 23, 0.6)";
        context.shadowBlur = 12;
        context.strokeRect(left, top, widthPx, heightPx);
        context.shadowBlur = 0;

        const badgeText = inferenceEvent
          ? `${track.track_id} | ${inferenceEvent.label} | ${Math.round(inferenceEvent.score * 100)}%`
          : `${track.track_id} | ${track.class_name ?? "person"} | ${Math.round(track.confidence * 100)}%`;
        const badgeWidth = Math.min(
          context.measureText(badgeText).width + 18,
          Math.max(widthPx, 120),
        );
        const badgeHeight = 26;
        const badgeTop = Math.max(top - badgeHeight - 6, displayRect.top);

        context.fillStyle = "rgba(2, 6, 23, 0.84)";
        context.fillRect(left, badgeTop, badgeWidth, badgeHeight);
        context.strokeStyle = color;
        context.strokeRect(left, badgeTop, badgeWidth, badgeHeight);
        context.fillStyle = color;
        context.fillText(badgeText, left + 9, badgeTop + badgeHeight / 2);
      });

      frameId = window.requestAnimationFrame(render);
    };

    frameId = window.requestAnimationFrame(render);
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [activeTracks, enabled, videoElement]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-20 size-full"
      aria-hidden="true"
    />
  );
}
