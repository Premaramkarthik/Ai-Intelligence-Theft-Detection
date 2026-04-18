"use client";

import Link from "next/link";
import { AlertTriangle, Camera, Network, Radar } from "lucide-react";

import { StreamCard } from "@/components/video/StreamCard";
import { DashboardSkeleton } from "@/components/skeletons/dashboard-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { useCameraList } from "@/modules/cameras/hooks";
import { useRealtimeOverview } from "@/modules/streams/hooks";

export function DashboardScreen() {
  const camerasQuery = useCameraList({ page: 1, page_size: 24 });
  const realtime = useRealtimeOverview();

  if (camerasQuery.isLoading) {
    return <DashboardSkeleton />;
  }

  const cameras = camerasQuery.data?.items ?? [];
  const activeCameras = cameras.filter((camera) => camera.status === "active");
  const liveFeeds = activeCameras.filter((camera) => realtime.streamIds.includes(camera.id)).length;
  const recentAlerts = realtime.recentActivity.filter((item) => item.tone === "critical" || item.tone === "warning").length;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader>
            <CardDescription>Active cameras</CardDescription>
            <CardTitle className="text-3xl">{activeCameras.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Live feeds</CardDescription>
            <CardTitle className="text-3xl">{liveFeeds}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Connection state</CardDescription>
            <div className="mt-2">
              <Badge tone={realtime.connectionState === "connected" ? "success" : realtime.connectionState === "reconnecting" ? "warning" : "danger"}>
                {realtime.connectionState}
              </Badge>
            </div>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Recent alerts</CardDescription>
            <CardTitle className="flex items-center gap-2 text-3xl">
              {recentAlerts}
              {recentAlerts > 0 ? <AlertTriangle className="h-5 w-5 text-[var(--warning-strong)]" /> : null}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {camerasQuery.error ? (
        <EmptyState
          title="Dashboard unavailable"
          description={camerasQuery.error instanceof Error ? camerasQuery.error.message : "Failed to load camera inventory from the backend."}
        />
      ) : activeCameras.length === 0 ? (
        <EmptyState
          title="No active streams"
          description="The dashboard only renders cameras marked active in the backend. Add a camera or change its status to active."
        />
      ) : (
        <div className="grid gap-5 xl:grid-cols-2">
          {activeCameras.map((camera) => (
            <StreamCard key={camera.id} camera={camera} />
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>System status</CardTitle>
              <CardDescription>Fast access to the main operational surfaces.</CardDescription>
            </div>
            <Badge tone="neutral">Live</Badge>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <Link href="/cameras" className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 transition-colors hover:bg-[var(--surface-2)]">
              <Camera className="h-5 w-5 text-[var(--accent-strong)]" />
              <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">Manage cameras</p>
            </Link>
            <Link href="/analytics" className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 transition-colors hover:bg-[var(--surface-2)]">
              <Radar className="h-5 w-5 text-[var(--accent-strong)]" />
              <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">View analytics</p>
            </Link>
            <Link href="/settings" className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 transition-colors hover:bg-[var(--surface-2)]">
              <Network className="h-5 w-5 text-[var(--accent-strong)]" />
              <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">Pipeline status</p>
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>Recent event activity</CardTitle>
              <CardDescription>Real-time websocket events arriving from the backend event bridge.</CardDescription>
            </div>
            <Button asChild variant="secondary" className="h-9">
              <Link href="/settings">Open diagnostics</Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {realtime.recentActivity.length > 0 ? (
              realtime.recentActivity.slice(0, 8).map((activity) => (
                <div
                  key={activity.id}
                  className="flex items-center justify-between rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3"
                >
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">{activity.label}</p>
                    <p className="text-xs text-[var(--text-secondary)]">
                      {activity.cameraId ? `${activity.cameraId} · ${activity.topic}` : activity.topic}
                    </p>
                  </div>
                  <Badge tone={activity.tone === "critical" ? "danger" : activity.tone === "warning" ? "warning" : activity.tone === "positive" ? "success" : "neutral"}>
                    {new Date(activity.timestamp).toLocaleTimeString()}
                  </Badge>
                </div>
              ))
            ) : (
              <EmptyState
                title="No event traffic yet"
                description="The websocket connection is established, but the dashboard has not received any stream, tracking, or inference events yet."
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

