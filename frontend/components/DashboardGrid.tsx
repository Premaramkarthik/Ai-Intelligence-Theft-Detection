"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { StreamCard } from "@/components/StreamCard";
import { deleteCamera } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import {
  buildGrafanaDashboardUrl,
  buildPrometheusTargetsUrl,
} from "@/lib/observability";
import { useStreamStore } from "@/store/streamStore";
import type { CameraResponse } from "@/types/stream";

interface DashboardGridProps {
  initialCameras: CameraResponse[];
}

export function DashboardGrid({ initialCameras }: DashboardGridProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);

  const hydrateCameras = useStreamStore((state) => state.hydrateCameras);
  const setCommandState = useStreamStore((state) => state.setCommandState);
  const clearCommandState = useStreamStore((state) => state.clearCommandState);
  const removeCamera = useStreamStore((state) => state.removeCamera);
  const cameraOrder = useStreamStore((state) => state.cameraOrder);
  const cameraMap = useStreamStore((state) => state.cameras);
  const streams = useStreamStore((state) => state.streams);

  useEffect(() => {
    hydrateCameras(initialCameras);
  }, [hydrateCameras, initialCameras]);

  useWebSocket();

  const cameras = useMemo(
    () =>
      cameraOrder
        .map((cameraId) => cameraMap[cameraId])
        .filter((camera): camera is CameraResponse => Boolean(camera)),
    [cameraMap, cameraOrder],
  );

  const visibleCameras = cameras.length > 0 ? cameras : initialCameras;

  const filteredCameras = visibleCameras.filter((camera) => {
    const searchable = [
      camera.name,
      camera.location ?? "",
      camera.rtsp_url_preview,
      camera.tags.join(" "),
    ]
      .join(" ")
      .toLowerCase();

    return searchable.includes(deferredQuery.trim().toLowerCase());
  });

  /**
   * Delete a camera from the dashboard after explicit operator confirmation.
   */
  const handleDelete = async (cameraId: string, cameraName: string) => {
    if (!window.confirm(`Delete camera "${cameraName}"? This cannot be undone.`)) {
      return;
    }

    setCommandState(
      cameraId,
      "deleting",
      "Deleting camera from the backend inventory.",
    );
    try {
      await deleteCamera(cameraId);
      removeCamera(cameraId);
      router.refresh();
    } catch {
      clearCommandState(cameraId);
    }
  };

  const liveCameraCount = filteredCameras.filter((camera) => {
    const status =
      streams[camera.id]?.streamInfo?.status ??
      camera.stream_status ??
      "stopped";
    return ["starting", "running", "reconnecting"].includes(status);
  }).length;

  const totalActiveTracks = filteredCameras.reduce((sum, camera) => {
    return sum + (streams[camera.id]?.streamInfo?.tracking?.active_tracks ?? 0);
  }, 0);

  const totalActiveInference = filteredCameras.reduce((sum, camera) => {
    return sum + (streams[camera.id]?.inferenceActiveEvents.length ?? 0);
  }, 0);

  return (
    <section className="screen-enter space-y-6">
      <div className="flex flex-col gap-4 rounded-[24px] border border-white/10 bg-slate-950/80 p-5 shadow-[0_18px_60px_rgba(0,0,0,0.24)] lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
            Dashboard
          </p>
          <h1 className="text-3xl font-semibold text-slate-50">
            Live camera streams
          </h1>
          <p className="max-w-2xl text-sm leading-6 text-slate-400">
            WebRTC is preferred for low-latency playback, HLS stays available as
            fallback, and tracker plus inference overlays are rendered directly
            on the raw feed.
          </p>
        </div>
        <div className="w-full max-w-sm space-y-3">
          <label className="block">
            <span className="mb-2 block text-xs uppercase tracking-[0.18em] text-slate-500">
              Search cameras
            </span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Front gate, warehouse, loading bay..."
              className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/cameras/new"
              className="rounded-full bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 ease-out hover:bg-amber-200"
            >
              Add camera
            </Link>
            <a
              href={buildGrafanaDashboardUrl()}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-500/20"
            >
              View Grafana
            </a>
            <a
              href={buildPrometheusTargetsUrl()}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 transition hover:border-cyan-300/30 hover:bg-white/5"
            >
              View Prometheus
            </a>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-[20px] border border-white/10 bg-slate-950/80 px-4 py-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Visible cameras</p>
          <p className="mt-2 text-3xl font-semibold text-slate-50">{filteredCameras.length}</p>
        </div>
        <div className="rounded-[20px] border border-white/10 bg-slate-950/80 px-4 py-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Live streams</p>
          <p className="mt-2 text-3xl font-semibold text-slate-50">{liveCameraCount}</p>
        </div>
        <div className="rounded-[20px] border border-white/10 bg-slate-950/80 px-4 py-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">
            Active overlays
          </p>
          <p className="mt-2 text-3xl font-semibold text-slate-50">
            {totalActiveTracks + totalActiveInference}
          </p>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-2 2xl:grid-cols-3">
        {filteredCameras.map((camera) => {
          const streamEntity = streams[camera.id];
          const streamInfo = streamEntity?.streamInfo;

          return (
            <StreamCard
              key={camera.id}
              camera={camera}
              initialStreamInfo={streamInfo ?? null}
              onDelete={() => void handleDelete(camera.id, camera.name)}
            />
          );
        })}
      </div>
    </section>
  );
}
