"use client";
/* eslint-disable @next/next/no-img-element */

import { AlertTriangle, ScanLine, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCameraRealtime, useRealtimeOverview } from "@/hooks/useRealtime";
import type { CameraResponse } from "@/types/camera";

function formatLastUpdate(isoTimestamp: string | null) {
  if (!isoTimestamp) {
    return "No live data yet";
  }
  return new Date(isoTimestamp).toLocaleTimeString();
}

export function StreamCard({ camera }: { camera: CameraResponse }) {
  const overview = useRealtimeOverview();
  const stream = useCameraRealtime(camera.id);
  const frame = stream.frame;
  const isConnected = overview.connectionState === "connected";
  const isBooting = !frame && (overview.connectionState === "connecting" || overview.connectionState === "reconnecting");

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
          {frame?.preview_jpeg_base64 ? (
            <img
              src={`data:image/jpeg;base64,${frame.preview_jpeg_base64}`}
              alt={`${camera.name} live frame`}
              className="absolute inset-0 h-full w-full object-contain"
            />
          ) : isBooting ? (
            <div className="absolute inset-0 p-4">
              <Skeleton className="h-full w-full rounded-2xl" />
            </div>
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center">
              {isConnected ? (
                <ScanLine className="h-8 w-8 text-[var(--text-secondary)]" />
              ) : (
                <WifiOff className="h-8 w-8 text-[var(--danger-strong)]" />
              )}
              <div>
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {isConnected ? "Awaiting live frames" : "Realtime connection unavailable"}
                </p>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  {isConnected
                    ? "The dashboard is connected, but this camera has not published a preview frame yet."
                    : "The websocket is reconnecting. Stream cards will resume automatically when data returns."}
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Pipeline</p>
            <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
              {frame ? `${frame.pipeline_latency_ms.toFixed(1)}ms` : "—"}
            </p>
          </div>
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Tracks</p>
            <p className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
              {stream.tracking?.active_tracks ?? frame?.active_tracks ?? 0}
            </p>
          </div>
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Alerts</p>
            <p className="mt-2 flex items-center gap-2 text-lg font-semibold text-[var(--text-primary)]">
              {stream.inference.filter((event) => event.alert_level !== "normal").length}
              {stream.inference.some((event) => event.alert_level === "alert") ? (
                <AlertTriangle className="h-4 w-4 text-[var(--danger-strong)]" />
              ) : null}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
