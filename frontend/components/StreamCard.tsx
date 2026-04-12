"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { TrackingCanvasOverlay } from "@/components/InferenceCanvasOverlay";
import { PlayerOverlay } from "@/components/PlayerOverlay";
import { StatusBadge } from "@/components/StatusBadge";
import { VideoPlayer } from "@/components/VideoPlayer";
import { useStream } from "@/hooks/useStream";
import type {
  BackendLifecycleState,
  CameraResponse,
  StreamCommandState,
  StreamInfoResponse,
} from "@/types/stream";

interface StreamCardProps {
  camera: CameraResponse;
  initialStreamInfo: StreamInfoResponse | null;
  onDelete: () => void;
}

function canStartStream(
  backendStatus: BackendLifecycleState,
  commandState: StreamCommandState,
): boolean {
  return (
    commandState === "idle" &&
    !["starting", "running", "reconnecting", "stopping"].includes(backendStatus)
  );
}

function canStopStream(
  backendStatus: BackendLifecycleState,
  commandState: StreamCommandState,
): boolean {
  return commandState === "idle" && !["stopped", "stopping"].includes(backendStatus);
}

function canDeleteCamera(commandState: StreamCommandState): boolean {
  return commandState === "idle";
}

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
    return "Start";
  }

  if (action === "delete") {
    return commandState === "deleting" ? "Deleting..." : "Delete";
  }

  return commandState === "stopping" ? "Stopping..." : "Stop";
}

export function StreamCard({
  camera,
  initialStreamInfo,
  onDelete,
}: StreamCardProps) {
  const tileRef = useRef<HTMLElement | null>(null);
  const [isVisible, setIsVisible] = useState(true);
  const {
    streamInfo,
    trackingInfo,
    inferenceInfo,
    activeInferenceEvents,
    recentInferenceAlerts,
    videoElement,
    backendLifecycle,
    commandState,
    commandMessage,
    playbackState,
    playbackProtocol,
    playbackMessage,
    playbackError,
    videoRef,
    retryPlayback,
    start,
    stop,
  } = useStream(camera.id, {
    initialCamera: camera,
    initialStreamInfo,
    autoStart: false,
    sampleFps: 5,
    subscribeToWebSocket: false,
    syncOnMount: false,
    playbackEnabled: isVisible,
    autoEnableInference: true,
  });

  useEffect(() => {
    const node = tileRef.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      return undefined;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsVisible(entry?.isIntersecting ?? true);
      },
      {
        threshold: 0.35,
        rootMargin: "200px 0px",
      },
    );
    observer.observe(node);

    return () => {
      observer.disconnect();
    };
  }, []);

  const backendErrorMessage = streamInfo?.last_error_message ?? null;
  const canStart = canStartStream(backendLifecycle, commandState);
  const canStop = canStopStream(backendLifecycle, commandState);
  const canDelete = canDeleteCamera(commandState);
  const latestAlert = recentInferenceAlerts[0] ?? null;
  const activeTrackCount = trackingInfo?.tracks.length ?? 0;
  const liveInferenceCount = activeInferenceEvents.length;

  return (
    <article
      ref={tileRef}
      className="overflow-hidden rounded-[24px] border border-white/10 bg-slate-950 shadow-[0_20px_70px_rgba(0,0,0,0.28)]"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/8 px-4 py-4">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">
            {camera.location ?? "Unassigned location"}
          </p>
          <h3 className="truncate text-xl font-semibold text-slate-50">
            {camera.name}
          </h3>
          <p className="mt-1 truncate text-sm text-slate-400">{camera.rtsp_url_preview}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge label={backendLifecycle} status={backendLifecycle} />
          <StatusBadge label={playbackState} status={playbackState} />
        </div>
      </div>

      <div className="px-4 pt-4">
        <VideoPlayer
          videoRef={videoRef}
          overlay={(
            <>
              <TrackingCanvasOverlay
                enabled={Boolean(trackingInfo?.enabled)}
                videoElement={videoElement}
                tracks={trackingInfo?.tracks ?? []}
                inferenceEvents={activeInferenceEvents}
              />
              <PlayerOverlay
                backendLifecycle={backendLifecycle}
                commandState={commandState}
                commandMessage={commandMessage}
                backendErrorMessage={backendErrorMessage}
                playbackState={playbackState}
                playbackProtocol={playbackProtocol}
                playbackMessage={playbackMessage}
                playbackError={playbackError}
                onRetry={retryPlayback}
              />
            </>
          )}
        />
      </div>

      <div className="space-y-4 px-4 py-4">
        <dl className="grid grid-cols-4 gap-3 text-sm">
          <div className="rounded-2xl border border-white/8 bg-slate-900/70 px-3 py-3">
            <dt className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
              FPS
            </dt>
            <dd className="mt-2 font-medium text-slate-100">
              {(streamInfo?.worker.current_fps ?? 0).toFixed(1).replace(/\.0$/, "")}
            </dd>
          </div>
          <div className="rounded-2xl border border-white/8 bg-slate-900/70 px-3 py-3">
            <dt className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
              Tracks
            </dt>
            <dd className="mt-2 font-medium text-slate-100">{activeTrackCount}</dd>
          </div>
          <div className="rounded-2xl border border-white/8 bg-slate-900/70 px-3 py-3">
            <dt className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
              Inference
            </dt>
            <dd className="mt-2 font-medium text-slate-100">{liveInferenceCount}</dd>
          </div>
          <div className="rounded-2xl border border-white/8 bg-slate-900/70 px-3 py-3">
            <dt className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
              Protocol
            </dt>
            <dd className="mt-2 font-medium text-slate-100">
              {playbackProtocol ?? "pending"}
            </dd>
          </div>
        </dl>

        {latestAlert ? (
          <div className="rounded-2xl border border-amber-400/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            Latest alert: {latestAlert.label} on track {latestAlert.local_track_id}
            {" "}
            ({latestAlert.score.toFixed(2)})
          </div>
        ) : null}

        {commandMessage ? (
          <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100">
            {commandMessage}
          </div>
        ) : null}

        {backendErrorMessage ? (
          <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {backendErrorMessage}
          </div>
        ) : null}

        {!streamInfo && backendLifecycle !== "stopped" ? (
          <div className="rounded-2xl border border-white/10 bg-slate-900/70 px-4 py-3 text-sm text-slate-300">
            Waiting for the latest stream contract from the backend.
          </div>
        ) : null}

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={start}
            disabled={!canStart}
            className="rounded-full bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {getActionLabel("start", commandState)}
          </button>
          <button
            type="button"
            onClick={stop}
            disabled={!canStop}
            className="rounded-full border border-white/12 px-4 py-2 text-sm font-semibold text-slate-100 transition hover:border-rose-400/40 hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {getActionLabel("stop", commandState)}
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={!canDelete}
            className="rounded-full border border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {getActionLabel("delete", commandState)}
          </button>
          <Link
            href={`/camera/${camera.id}`}
            className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-500/20"
          >
            Open player
          </Link>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
          <span>Transport {camera.transport}</span>
          <span>Source {camera.source_mode}</span>
          <span>
            Queue {(streamInfo?.worker.queue_latency_ms ?? 0).toFixed(1).replace(/\.0$/, "")}
            {" "}ms
          </span>
          <span>Drops {streamInfo?.worker.dropped_frames ?? 0}</span>
          <span>
            Inference {inferenceInfo?.enabled ? (inferenceInfo.healthy ? "ready" : "degraded") : "idle"}
          </span>
        </div>
      </div>
    </article>
  );
}
