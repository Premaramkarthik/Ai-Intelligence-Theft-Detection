"use client";

import Link from "next/link";

import { StatusBadge } from "@/components/StatusBadge";
import type {
  BackendLifecycleState,
  CameraResponse,
  StreamCommandState,
  WorkerStateResponse,
} from "@/types/stream";

interface StreamCardProps {
  camera: CameraResponse;
  backendStatus: BackendLifecycleState;
  commandState: StreamCommandState;
  commandMessage: string | null;
  backendErrorMessage: string | null;
  worker: WorkerStateResponse | null;
  onStart: () => void;
  onStop: () => void;
  onDelete: () => void;
}

/**
 * Decide whether a stream can accept a start action from the dashboard.
 */
function canStartStream(
  backendStatus: BackendLifecycleState,
  commandState: StreamCommandState,
): boolean {
  return (
    commandState === "idle" &&
    !["starting", "running", "reconnecting", "stopping"].includes(backendStatus)
  );
}

/**
 * Decide whether a stream can accept a stop action from the dashboard.
 */
function canStopStream(
  backendStatus: BackendLifecycleState,
  commandState: StreamCommandState,
): boolean {
  return commandState === "idle" && !["stopped", "stopping"].includes(backendStatus);
}

/**
 * Decide whether a camera can be deleted without conflicting with another active command.
 */
function canDeleteCamera(commandState: StreamCommandState): boolean {
  return commandState === "idle";
}

/**
 * Render intent-aware button copy from the current control-plane command state.
 */
function getActionLabel(
  action: "start" | "stop" | "delete",
  commandState: StreamCommandState,
): string {
  if (action === "start") {
    if (commandState === "starting") {
      return "Connecting...";
    }
    if (commandState === "restarting") {
      return "Reconnecting...";
    }
    if (commandState === "refreshing") {
      return "Refreshing...";
    }
    return "Start";
  }

  if (action === "delete") {
    return commandState === "deleting" ? "Deleting..." : "Delete";
  }

  if (commandState === "stopping") {
    return "Stopping...";
  }
  return "Stop";
}

export function StreamCard({
  camera,
  backendStatus,
  commandState,
  commandMessage,
  backendErrorMessage,
  worker,
  onStart,
  onStop,
  onDelete,
}: StreamCardProps) {
  const canStart = canStartStream(backendStatus, commandState);
  const canStop = canStopStream(backendStatus, commandState);
  const canDelete = canDeleteCamera(commandState);

  return (
    <article className="card-enter group overflow-hidden rounded-[28px] border border-white/8 bg-[linear-gradient(160deg,rgba(17,32,42,0.92),rgba(10,16,22,0.92))] shadow-[0_24px_90px_rgba(0,0,0,0.34)] transition-all duration-300 ease-out hover:-translate-y-1 hover:border-cyan-300/20 hover:shadow-[0_28px_120px_rgba(0,0,0,0.42)]">
      <div className="border-b border-white/6 bg-[radial-gradient(circle_at_top_left,_rgba(45,212,191,0.16),_transparent_38%),radial-gradient(circle_at_top_right,_rgba(251,191,36,0.12),_transparent_32%)] px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-slate-400">
              {camera.location ?? "Unassigned location"}
            </p>
            <h3 className="text-2xl font-semibold text-slate-50">
              {camera.name}
            </h3>
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Camera ID {camera.id}
            </p>
            <p className="text-sm text-slate-400">{camera.rtsp_url_preview}</p>
          </div>
          <StatusBadge label={backendStatus} status={backendStatus} />
        </div>
      </div>
      <div className="space-y-5 px-5 py-5">
        <dl className="grid grid-cols-2 gap-4 text-sm text-slate-300">
          <div className="rounded-2xl border border-white/6 bg-slate-950/55 p-4">
            <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Source
            </dt>
            <dd className="mt-2 font-medium text-slate-100">{camera.source_mode}</dd>
          </div>
          <div className="rounded-2xl border border-white/6 bg-slate-950/55 p-4">
            <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Transport
            </dt>
            <dd className="mt-2 font-medium text-slate-100">{camera.transport}</dd>
          </div>
        </dl>
        <dl className="grid grid-cols-3 gap-3 text-sm text-slate-300">
          <div className="rounded-2xl border border-white/6 bg-slate-950/55 p-4">
            <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">
              FPS
            </dt>
            <dd className="mt-2 font-medium text-slate-100">
              {(worker?.current_fps ?? 0).toFixed(1).replace(/\.0$/, "")}
            </dd>
          </div>
          <div className="rounded-2xl border border-white/6 bg-slate-950/55 p-4">
            <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Queue
            </dt>
            <dd className="mt-2 font-medium text-slate-100">
              {(worker?.queue_latency_ms ?? 0).toFixed(1).replace(/\.0$/, "")} ms
            </dd>
          </div>
          <div className="rounded-2xl border border-white/6 bg-slate-950/55 p-4">
            <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Drops
            </dt>
            <dd className="mt-2 font-medium text-slate-100">
              {worker?.dropped_frames ?? 0}
            </dd>
          </div>
        </dl>
        {commandMessage ? (
          <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100 transition-all duration-300 ease-out">
            {commandMessage}
          </div>
        ) : null}
        {backendErrorMessage ? (
          <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100 transition-all duration-300 ease-out">
            {backendErrorMessage}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onStart}
            disabled={!canStart}
            className="rounded-full bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 ease-out hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {getActionLabel("start", commandState)}
          </button>
          <button
            type="button"
            onClick={onStop}
            disabled={!canStop}
            className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 transition-all duration-300 ease-out hover:border-rose-400/40 hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {getActionLabel("stop", commandState)}
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={!canDelete}
            className="rounded-full border border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 transition-all duration-300 ease-out hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {getActionLabel("delete", commandState)}
          </button>
          <Link
            href={`/camera/${camera.id}`}
            className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition-all duration-300 ease-out hover:bg-cyan-500/20"
          >
            Open player
          </Link>
        </div>
      </div>
    </article>
  );
}
