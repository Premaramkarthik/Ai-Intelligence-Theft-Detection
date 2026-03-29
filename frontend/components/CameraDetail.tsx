"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { PlayerOverlay } from "@/components/PlayerOverlay";
import { StatusBadge } from "@/components/StatusBadge";
import { VideoPlayer } from "@/components/VideoPlayer";
import { WorkerMetricsPanel } from "@/components/WorkerMetricsPanel";
import { useStream } from "@/hooks/useStream";
import { deleteCamera } from "@/lib/api";
import { useStreamStore } from "@/store/streamStore";
import type {
  BackendLifecycleState,
  CameraResponse,
  StreamCommandState,
  StreamInfoResponse,
} from "@/types/stream";

interface CameraDetailProps {
  cameraId: string;
  initialCamera: CameraResponse | null;
  initialStreamInfo: StreamInfoResponse | null;
}

/**
 * Decide whether the dedicated player screen should offer a start action.
 */
function canStartAction(
  backendLifecycle: BackendLifecycleState,
  commandState: StreamCommandState,
): boolean {
  return (
    commandState === "idle" &&
    !["starting", "running", "reconnecting", "stopping"].includes(backendLifecycle)
  );
}

/**
 * Decide whether the dedicated player screen should offer a stop action.
 */
function canStopAction(
  backendLifecycle: BackendLifecycleState,
  commandState: StreamCommandState,
): boolean {
  return commandState === "idle" && !["stopped", "stopping"].includes(backendLifecycle);
}

/**
 * Render action-aware button labels for the camera detail controls.
 */
function getControlLabel(
  control: "start" | "restart" | "stop" | "refresh",
  commandState: StreamCommandState,
): string {
  if (control === "start") {
    return commandState === "starting" ? "Connecting..." : "Start";
  }
  if (control === "restart") {
    return commandState === "restarting" ? "Reconnecting..." : "Force reconnect";
  }
  if (control === "stop") {
    return commandState === "stopping" ? "Stopping..." : "Stop";
  }
  return commandState === "refreshing" ? "Refreshing..." : "Refresh state";
}

export function CameraDetail({
  cameraId,
  initialCamera,
  initialStreamInfo,
}: CameraDetailProps) {
  const router = useRouter();
  const setCommandState = useStreamStore((state) => state.setCommandState);
  const clearCommandState = useStreamStore((state) => state.clearCommandState);
  const removeCamera = useStreamStore((state) => state.removeCamera);
  const {
    camera,
    streamInfo,
    backendLifecycle,
    commandState,
    commandMessage,
    playbackState,
    playbackProtocol,
    playbackMessage,
    playbackError,
    videoRef,
    refresh,
    retryPlayback,
    start,
    forceRestart,
    stop,
  } = useStream(cameraId, {
    initialCamera,
    initialStreamInfo,
    autoStart: true,
    sampleFps: 1,
  });

  const startDisabled = !canStartAction(backendLifecycle, commandState);
  const stopDisabled = !canStopAction(backendLifecycle, commandState);
  const restartDisabled =
    commandState !== "idle" ||
    !["starting", "running", "reconnecting"].includes(backendLifecycle);
  const refreshDisabled = commandState !== "idle";
  const deleteDisabled = commandState !== "idle";

  /**
   * Delete the current camera and return the operator to the dashboard.
   */
  const handleDelete = async () => {
    const cameraName = camera?.name ?? cameraId;
    if (!window.confirm(`Delete camera "${cameraName}"? This cannot be undone.`)) {
      return;
    }

    setCommandState(cameraId, "deleting", "Deleting camera from the backend inventory.");
    try {
      await deleteCamera(cameraId);
      removeCamera(cameraId);
      router.push("/dashboard");
      router.refresh();
    } catch {
      clearCommandState(cameraId);
    }
  };

  return (
    <section className="screen-enter space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-2">
          <Link
            href="/dashboard"
            className="text-sm font-medium text-sky-300 transition-all duration-300 ease-out hover:text-sky-200"
          >
            ← Back to dashboard
          </Link>
          <h1 className="text-4xl font-semibold text-slate-50">
            {camera?.name ?? cameraId}
          </h1>
          <p className="max-w-2xl text-base leading-7 text-slate-400">
            The backend controls lifecycle state. The player handles media
            transport only and falls back to HLS when WebRTC cannot be
            maintained.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <StatusBadge label={backendLifecycle} status={backendLifecycle} />
          <StatusBadge label={playbackState} status={playbackState} />
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(340px,0.9fr)]">
        <div className="space-y-4">
          <VideoPlayer
            videoRef={videoRef}
            overlay={
              <PlayerOverlay
                backendLifecycle={backendLifecycle}
                commandState={commandState}
                commandMessage={commandMessage}
                backendErrorMessage={streamInfo?.last_error_message ?? null}
                playbackState={playbackState}
                playbackProtocol={playbackProtocol}
                playbackMessage={playbackMessage}
                playbackError={playbackError}
                onRetry={retryPlayback}
              />
            }
          />
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={start}
              disabled={startDisabled}
              className="rounded-full bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 ease-out hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {getControlLabel("start", commandState)}
            </button>
            <button
              type="button"
              onClick={forceRestart}
              disabled={restartDisabled}
              className="rounded-full border border-sky-400/30 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-200 transition-all duration-300 ease-out hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {getControlLabel("restart", commandState)}
            </button>
            <button
              type="button"
              onClick={stop}
              disabled={stopDisabled}
              className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 transition-all duration-300 ease-out hover:border-rose-400/40 hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {getControlLabel("stop", commandState)}
            </button>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={refreshDisabled}
              className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 transition-all duration-300 ease-out hover:border-white/20 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {getControlLabel("refresh", commandState)}
            </button>
            <button
              type="button"
              onClick={() => void handleDelete()}
              disabled={deleteDisabled}
              className="rounded-full border border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 transition-all duration-300 ease-out hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {commandState === "deleting" ? "Deleting..." : "Delete camera"}
            </button>
          </div>
          {commandMessage ? (
            <div className="rounded-2xl border border-sky-400/20 bg-sky-500/10 px-4 py-3 text-sm text-sky-100 transition-all duration-300 ease-out">
              {commandMessage}
            </div>
          ) : null}
          {streamInfo?.last_error_message ? (
            <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100 transition-all duration-300 ease-out">
              {streamInfo.last_error_message}
            </div>
          ) : null}
          <WorkerMetricsPanel worker={streamInfo?.worker ?? null} />
        </div>

        <aside className="space-y-5">
          <div className="rounded-[28px] border border-white/8 bg-slate-800/80 p-5">
            <h2 className="text-lg font-semibold text-slate-50">Playback contract</h2>
            <dl className="mt-4 space-y-4 text-sm text-slate-300">
              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">
                  WebRTC
                </dt>
                <dd className="mt-2 break-all text-slate-100">
                  {streamInfo?.access_urls.webrtc_url ?? "Not available yet"}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">
                  HLS fallback
                </dt>
                <dd className="mt-2 break-all text-slate-100">
                  {streamInfo?.access_urls.hls_url ?? "Not available yet"}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">
                  WebSocket
                </dt>
                <dd className="mt-2 break-all text-slate-100">
                  {streamInfo?.websocket_url ?? "Using default backend updates URL"}
                </dd>
              </div>
            </dl>
          </div>
        </aside>
      </div>
    </section>
  );
}
