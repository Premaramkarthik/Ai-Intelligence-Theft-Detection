"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { TrackingCanvasOverlay } from "@/components/InferenceCanvasOverlay";
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
  PlaybackViewMode,
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

function sourceButtonClasses(
  isActive: boolean,
  isDisabled: boolean,
): string {
  if (isActive) {
    return "border-teal-300/40 bg-teal-400/15 text-teal-100";
  }
  if (isDisabled) {
    return "cursor-not-allowed border-white/5 bg-white/[0.02] text-slate-500";
  }
  return "border-white/10 bg-white/[0.03] text-slate-200 hover:border-white/20 hover:bg-white/[0.06]";
}

function getSourceDescription(
  playbackViewMode: PlaybackViewMode,
): string {
  return playbackViewMode === "tracked"
    ? "Showing annotated tracking video with IDs burned into the stream."
    : "Showing the raw camera feed without tracking overlays.";
}

export function CameraDetail({
  cameraId,
  initialCamera,
  initialStreamInfo,
}: CameraDetailProps) {
  const router = useRouter();
  const [trackingOverlayEnabled, setTrackingOverlayEnabled] = useState(true);
  const setCommandState = useStreamStore((state) => state.setCommandState);
  const clearCommandState = useStreamStore((state) => state.clearCommandState);
  const removeCamera = useStreamStore((state) => state.removeCamera);
  const {
    camera,
    streamInfo,
    trackingInfo,
    videoElement,
    playbackViewMode,
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
    setPlaybackViewMode,
    isTrackedPlaybackAvailable,
    start,
    forceRestart,
    stop,
  } = useStream(cameraId, {
    initialCamera,
    initialStreamInfo,
    autoStart: true,
    sampleFps: 5,
  });

  const overlayEligible =
    playbackViewMode === "raw" && Boolean(trackingInfo?.enabled);

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
            className="text-sm font-medium text-cyan-300 transition-all duration-300 ease-out hover:text-cyan-200"
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
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex rounded-full border border-white/10 bg-slate-950/65 p-1">
              <button
                type="button"
                onClick={() => setPlaybackViewMode("raw")}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition-all duration-300 ease-out ${sourceButtonClasses(
                  playbackViewMode === "raw",
                  false,
                )}`}
              >
                Raw feed
              </button>
              <button
                type="button"
                onClick={() => setPlaybackViewMode("tracked")}
                disabled={!isTrackedPlaybackAvailable}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition-all duration-300 ease-out ${sourceButtonClasses(
                  playbackViewMode === "tracked",
                  !isTrackedPlaybackAvailable,
                )}`}
              >
                Tracked feed
              </button>
            </div>
            {overlayEligible ? (
              <button
                type="button"
                onClick={() => setTrackingOverlayEnabled((value) => !value)}
                className={`rounded-full border px-4 py-2 text-sm font-semibold transition-all duration-300 ease-out ${
                  trackingOverlayEnabled
                    ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100 hover:bg-emerald-500/20"
                    : "border-white/10 bg-white/[0.03] text-slate-200 hover:border-white/20 hover:bg-white/[0.06]"
                }`}
              >
                {trackingOverlayEnabled ? "Tracking overlay on" : "Tracking overlay off"}
              </button>
            ) : null}
            <p className="text-sm text-slate-400">
              {getSourceDescription(playbackViewMode)}
            </p>
          </div>
          <VideoPlayer
            videoRef={videoRef}
            overlay={
              <>
                <TrackingCanvasOverlay
                  enabled={overlayEligible && trackingOverlayEnabled}
                  videoElement={videoElement}
                  tracks={trackingInfo?.tracks ?? []}
                />
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
              </>
            }
          />
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={start}
              disabled={startDisabled}
              className="rounded-full bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 ease-out hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {getControlLabel("start", commandState)}
            </button>
            <button
              type="button"
              onClick={forceRestart}
              disabled={restartDisabled}
              className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition-all duration-300 ease-out hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60"
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
            <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100 transition-all duration-300 ease-out">
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
          <div className="rounded-[28px] border border-white/8 bg-[linear-gradient(160deg,rgba(17,32,42,0.92),rgba(9,18,24,0.92))] p-5">
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
                  Tracked WebRTC
                </dt>
                <dd className="mt-2 break-all text-slate-100">
                  {trackingInfo?.access_urls?.webrtc_url ?? "Tracked stream not ready yet"}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">
                  Tracked HLS
                </dt>
                <dd className="mt-2 break-all text-slate-100">
                  {trackingInfo?.access_urls?.hls_url ?? "Tracked stream not ready yet"}
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


          <div className="rounded-[28px] border border-white/8 bg-[linear-gradient(160deg,rgba(17,32,42,0.92),rgba(9,18,24,0.92))] p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-50">Tracked objects</h2>
                <p className="mt-1 text-sm text-slate-400">
                  Live metadata from the backend tracking contract.
                </p>
              </div>
              <StatusBadge
                label={`${trackingInfo?.active_tracks ?? 0} active`}
                status={
                  trackingInfo?.enabled && trackingInfo.is_process_alive
                    ? "running"
                    : "stopped"
                }
              />
            </div>

            {trackingInfo?.tracks.length ? (
              <div className="mt-4 space-y-3">
                {trackingInfo.tracks.map((track) => (
                  <div
                    key={`${track.track_id}-${track.persistent_id ?? "pending"}`}
                    className="rounded-2xl border border-white/8 bg-slate-900/60 px-4 py-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-slate-100">
                          Track {track.track_id}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500">
                          {track.class_name ?? "person"}
                        </p>
                      </div>
                      <div className="text-right text-sm text-slate-300">
                        <p>
                          Persistent ID:{" "}
                          <span className="font-medium text-emerald-200">
                            {track.persistent_id ?? "Assigning..."}
                          </span>
                        </p>
                        <p className="mt-1 text-xs text-slate-400">
                          Confidence {track.confidence.toFixed(2)}
                          {track.similarity !== null
                            ? ` • similarity ${track.similarity.toFixed(2)}`
                            : ""}
                        </p>
                      </div>
                    </div>
                    <p className="mt-3 text-xs text-slate-400">
                      BBox: x={track.left}, y={track.top}, w={track.width}, h={track.height}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-dashed border-white/10 bg-slate-900/40 px-4 py-5 text-sm text-slate-400">
                {trackingInfo?.enabled
                  ? "Tracking is enabled. Person IDs will appear here when detections are active."
                  : "Tracking is not active for this stream yet."}
              </div>
            )}
          </div>

        </aside>
      </div>
    </section>
  );
}
