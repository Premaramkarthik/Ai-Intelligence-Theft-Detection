"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { deleteCamera } from "@/lib/api";
import {
  buildGrafanaDashboardUrl,
  buildPrometheusTargetsUrl,
} from "@/lib/observability";
import type { CameraResponse } from "@/types/camera";

interface DashboardGridProps {
  initialCameras: CameraResponse[];
}

export function DashboardGrid({ initialCameras }: DashboardGridProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);

  const cameras = initialCameras;

  const visibleCameras = cameras;

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

    try {
      await deleteCamera(cameraId);
      router.refresh();
    } catch {
      // ignore
    }
  };

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
            Cameras and their details are listed here. Stream access is currently disabled.
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
          <p className="mt-2 text-3xl font-semibold text-slate-50">0</p>
        </div>
        <div className="rounded-[20px] border border-white/10 bg-slate-950/80 px-4 py-4">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">
            Active overlays
          </p>
          <p className="mt-2 text-3xl font-semibold text-slate-50">
            0
          </p>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-2 2xl:grid-cols-3">
        {filteredCameras.map((camera) => (
          <div key={camera.id} className="rounded-[20px] border border-white/10 bg-slate-950/80 p-5">
            <h2 className="text-lg font-semibold text-slate-50">{camera.name}</h2>
            <p className="text-sm text-slate-400">{camera.location ?? "No location"}</p>
            <div className="mt-4 flex gap-3">
              <Link href={`/camera/${camera.id}`} className="rounded-full bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950">
                View Details
              </Link>
              <button
                type="button"
                onClick={() => void handleDelete(camera.id, camera.name)}
                className="rounded-full border border-rose-400/30 px-4 py-2 text-sm font-semibold text-rose-300"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
