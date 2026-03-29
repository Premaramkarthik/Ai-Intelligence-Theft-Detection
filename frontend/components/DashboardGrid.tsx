"use client";

import Link from "next/link";
import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { StreamCard } from "@/components/StreamCard";
import { deleteCamera, startStream, stopStream } from "@/lib/api";
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
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);

  const hydrateCameras = useStreamStore((state) => state.hydrateCameras);
  const upsertStreamInfo = useStreamStore((state) => state.upsertStreamInfo);
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
   * Start a camera from the dashboard while keeping the card controls in sync with backend commands.
   */
  const handleStart = async (cameraId: string) => {
    setCommandState(
      cameraId,
      "starting",
      "Sending start request to the backend control plane.",
    );
    try {
      const streamInfo = await startStream(cameraId, {
        requested_protocol: "webrtc",
        sample_fps: 1,
        enable_tracking_events: false,
        reason: "dashboard_start_request",
      });
      upsertStreamInfo(streamInfo);
    } catch {
      clearCommandState(cameraId);
    }
  };

  /**
   * Stop a camera from the dashboard without allowing repeated clicks during shutdown.
   */
  const handleStop = async (cameraId: string) => {
    setCommandState(
      cameraId,
      "stopping",
      "Sending stop request to the backend control plane.",
    );
    try {
      const streamInfo = await stopStream(cameraId, {
        reason: "dashboard_stop_request",
      });
      upsertStreamInfo(streamInfo);
    } catch {
      clearCommandState(cameraId);
    }
  };

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
    } catch {
      clearCommandState(cameraId);
    }
  };

  return (
    <section className="screen-enter space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.26em] text-sky-300">
            Real-time CCTV dashboard
          </p>
          <h1 className="text-4xl font-semibold text-slate-50">
            Live camera control plane
          </h1>
          <p className="max-w-2xl text-base leading-7 text-slate-400">
            WebRTC is reserved for playback, backend state comes from the API and
            WebSocket, and streams stay dormant until an operator opens them.
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
              className="w-full rounded-2xl border border-white/10 bg-slate-900/80 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-sky-400/40"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/cameras/new"
              className="rounded-full bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 ease-out hover:bg-emerald-400"
            >
              Add camera
            </Link>
            <a
              href={buildGrafanaDashboardUrl()}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-sky-400/30 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-200 transition-all duration-300 ease-out hover:bg-sky-500/20"
            >
              View Grafana
            </a>
            <a
              href={buildPrometheusTargetsUrl()}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 transition-all duration-300 ease-out hover:border-white/20 hover:bg-white/5"
            >
              View Prometheus
            </a>
          </div>
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {filteredCameras.map((camera) => {
          const streamEntity = streams[camera.id];
          const streamInfo = streamEntity?.streamInfo;
          const backendStatus =
            streamInfo?.status ?? camera.stream_status ?? "stopped";

          return (
            <StreamCard
              key={camera.id}
              camera={camera}
              backendStatus={backendStatus}
              commandState={streamEntity?.commandState ?? "idle"}
              commandMessage={streamEntity?.commandMessage ?? null}
              backendErrorMessage={streamInfo?.last_error_message ?? null}
              worker={streamInfo?.worker ?? null}
              onStart={() => void handleStart(camera.id)}
              onStop={() => void handleStop(camera.id)}
              onDelete={() => void handleDelete(camera.id, camera.name)}
            />
          );
        })}
      </div>
    </section>
  );
}
