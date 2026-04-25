"use client";

import { AlertTriangle, RefreshCw, ScanLine, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useWebRTCStream } from "@/hooks/useWebRTCStream";
import { useCameraRealtime, useRealtimeOverview } from "@/hooks/useRealtime";
import type { CameraResponse } from "@/types/camera";
import type { InferenceEvent } from "@/types/realtime";

function alertTone(level: string): "success" | "warning" | "danger" | "neutral" {
  if (level === "alert") return "danger";
  if (level === "warning") return "warning";
  if (level === "normal") return "success";
  return "neutral";
}

/** Keep only the most recent inference event for this camera and track. */
function latestPerTrack(events: InferenceEvent[], cameraId: string): InferenceEvent[] {
  const seen = new Set<string>();
  const result: InferenceEvent[] = [];
  for (const ev of events) {
    if (ev.camera_id !== cameraId) {
      continue;
    }
    const trackKey = ev.local_track_id;
    if (!seen.has(trackKey)) {
      seen.add(trackKey);
      result.push(ev);
    }
  }
  return result.slice(0, 8);
}

function formatLastUpdate(isoTimestamp: string | null) {
  if (!isoTimestamp) {
    return "No live data yet";
  }
  return new Date(isoTimestamp).toLocaleTimeString();
}

export function StreamCard({ camera }: { camera: CameraResponse }) {
  const overview = useRealtimeOverview();
  const stream = useCameraRealtime(camera.id);
  const { videoRef, state: rtcState, attempt, maxAttempts, restart } = useWebRTCStream(camera.id);
  const frame = stream.frame?.camera_id === camera.id ? stream.frame : null;
  const tracking = stream.tracking?.camera_id === camera.id ? stream.tracking : null;
  const inference = latestPerTrack(stream.inference, camera.id);

  const isWsConnected = overview.connectionState === "connected";
  const isRtcConnected = rtcState === "connected";
  const isBooting = rtcState === "connecting" || rtcState === "idle";
  const isRetrying = rtcState === "retrying";
  const isFailed = rtcState === "failed" || rtcState === "closed";

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-start justify-between gap-4 border-b border-[var(--border-subtle)]">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Camera</p>
          <CardTitle className="mt-2 text-lg">{camera.name}</CardTitle>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {camera.location ?? "No location"} · {camera.status}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <Badge tone={camera.status === "active" ? "success" : "neutral"}>{camera.status}</Badge>
          <span className="text-xs text-[var(--text-secondary)]">
            {formatLastUpdate(stream.lastUpdatedAt)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="relative aspect-video overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)]">
          {/* WebRTC video — bounding boxes are burned in by the Python backend */}
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className={`absolute inset-0 h-full w-full object-contain transition-opacity duration-300 ${
              isRtcConnected ? "opacity-100" : "opacity-0"
            }`}
          />

          {/* Loading / error states shown while video is not live */}
          {!isRtcConnected && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center">
              {isBooting || isRetrying ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-4">
                  <Skeleton className="absolute inset-0 h-full w-full rounded-2xl" />
                  {isRetrying && (
                    <p className="relative z-10 text-xs font-medium text-[var(--text-secondary)]">
                      Retry {attempt}/{maxAttempts}…
                    </p>
                  )}
                </div>
              ) : isFailed ? (
                <>
                  <WifiOff className="h-8 w-8 text-[var(--danger-strong)]" />
                  <div>
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      WebRTC connection failed
                    </p>
                    <p className="mt-1 text-sm text-[var(--text-secondary)]">
                      Check that the camera is active and the backend is reachable.
                    </p>
                  </div>
                  <button
                    onClick={restart}
                    className="mt-2 flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--surface-3)] transition-colors"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Retry
                  </button>
                </>
              ) : !isWsConnected ? (
                <>
                  <WifiOff className="h-8 w-8 text-[var(--danger-strong)]" />
                  <div>
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      Realtime connection unavailable
                    </p>
                    <p className="mt-1 text-sm text-[var(--text-secondary)]">
                      The WebSocket is reconnecting. Stream cards will resume automatically.
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <ScanLine className="h-8 w-8 text-[var(--text-secondary)]" />
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Awaiting WebRTC stream
                  </p>
                </>
              )}
            </div>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Pipeline</p>
            <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
              {frame ? `${frame.pipeline_latency_ms.toFixed(1)}ms` : "-"}
            </p>
          </div>
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Tracks</p>
            <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
              {tracking?.active_tracks ?? frame?.active_tracks ?? 0}
            </p>
          </div>
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Alerts</p>
            <p className="mt-2 flex items-center gap-2 text-lg font-semibold text-[var(--text-primary)]">
              {inference.filter((event) => event.alert_level !== "normal").length}
              {inference.some((event) => event.alert_level === "alert") ? (
                <AlertTriangle className="h-4 w-4 text-[var(--danger-strong)]" />
              ) : null}
            </p>
          </div>
        </div>

        {/* Per-track inference labels — scoped to this camera only */}
        {inference.length > 0 && (
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
            <p className="mb-2.5 text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">
              Inference - {camera.name}
            </p>
            <div className="space-y-2">
              {inference.map((event) => (
                <div
                  key={`${event.camera_id}-${event.local_track_id}`}
                  className="flex items-center justify-between gap-3"
                >
                  <span className="truncate text-sm font-medium text-[var(--text-secondary)]">
                    {event.persistent_id ?? event.local_track_id}
                  </span>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-xs tabular-nums text-[var(--text-muted)]">
                      {(event.score * 100).toFixed(0)}%
                    </span>
                    <Badge tone={alertTone(event.alert_level)}>{event.alert_level}</Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
