"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
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
  const router = useRouter();
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
        sample_fps: 5,
        enable_tracking_events: true,
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
      router.refresh();
    } catch {
      clearCommandState(cameraId);
    }
  };

  return (
    <section className="screen-enter space-y-6">
      <div className="flex flex-col gap-4 rounded-[32px] border border-white/8 bg-[linear-gradient(140deg,rgba(17,32,42,0.94),rgba(9,18,24,0.90)),radial-gradient(circle_at_top_right,rgba(45,212,191,0.16),transparent_28%),radial-gradient(circle_at_bottom_left,rgba(251,191,36,0.10),transparent_24%)] p-6 shadow-[0_30px_120px_rgba(0,0,0,0.38)] lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.26em] text-cyan-300">
            Sentinel operations deck
          </p>
          <h1 className="text-4xl font-semibold text-slate-50">
            Live surveillance control plane
          </h1>
          <p className="max-w-2xl text-base leading-7 text-slate-300">
            Raw playback, tracked playback, worker health, and observability links
            stay in one operator-first workspace so camera issues can be triaged
            without hopping between tools.
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
              className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition-all duration-300 ease-out hover:bg-cyan-500/20"
            >
              View Grafana
            </a>
            <a
              href={buildPrometheusTargetsUrl()}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 transition-all duration-300 ease-out hover:border-cyan-300/30 hover:bg-white/5"
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
