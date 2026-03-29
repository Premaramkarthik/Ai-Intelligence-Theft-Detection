import type {
  BackendLifecycleState,
  PlaybackState,
  StreamCommandState,
  StreamProtocol,
} from "@/types/stream";

interface PlayerOverlayProps {
  backendLifecycle: BackendLifecycleState;
  commandState: StreamCommandState;
  commandMessage: string | null;
  backendErrorMessage: string | null;
  playbackState: PlaybackState;
  playbackProtocol: StreamProtocol | null;
  playbackMessage: string | null;
  playbackError: string | null;
  onRetry: () => void;
}

function buildOverlayCopy(
  backendLifecycle: BackendLifecycleState,
  commandState: StreamCommandState,
  commandMessage: string | null,
  backendErrorMessage: string | null,
  playbackState: PlaybackState,
  playbackProtocol: StreamProtocol | null,
  playbackMessage: string | null,
  playbackError: string | null,
) {
  if (playbackError) {
    return {
      title: "Playback attention required",
      body: playbackError,
      tone: "error",
    } as const;
  }

  if (
    backendErrorMessage &&
    (backendLifecycle === "error" ||
      backendLifecycle === "reconnecting" ||
      backendLifecycle === "crashed")
  ) {
    return {
      title: "Backend reported a stream issue",
      body: backendErrorMessage,
      tone: "error",
    } as const;
  }

  if (commandState === "starting" || commandState === "restarting") {
    return {
      title: commandState === "restarting" ? "Restarting live feed" : "Connecting to live feed",
      body:
        commandMessage ??
        "The backend accepted the command and is preparing the stream path.",
      tone: "info",
    } as const;
  }

  if (commandState === "stopping") {
    return {
      title: "Stopping stream",
      body: commandMessage ?? "The backend is shutting down the current stream.",
      tone: "neutral",
    } as const;
  }

  if (backendLifecycle === "reconnecting" || playbackState === "recovering") {
    return {
      title: "Recovering stream",
      body:
        playbackMessage ??
        "The backend is reconnecting to the source. Playback will resume automatically when frames return.",
      tone: "warning",
    } as const;
  }

  if (playbackState === "loading" || backendLifecycle === "starting") {
    return {
      title: "Connecting to live feed",
      body:
        playbackMessage ??
        "Negotiating the WebRTC session and waiting for the first frames.",
      tone: "info",
    } as const;
  }

  if (playbackState === "buffering") {
    return {
      title: "Buffering live stream",
      body:
        playbackMessage ??
        "Media is temporarily stalled. The player is waiting for frames to resume.",
      tone: "info",
    } as const;
  }

  if (playbackState === "degraded" && playbackProtocol === "hls") {
    return {
      title: "HLS fallback active",
      body:
        playbackMessage ??
        "WebRTC could not be maintained, so the player switched to HLS for continuity.",
      tone: "warning",
    } as const;
  }

  if (backendLifecycle === "stopped") {
    return {
      title: "Stream is stopped",
      body: "Start the camera stream to begin playback.",
      tone: "neutral",
    } as const;
  }

  return null;
}

export function PlayerOverlay({
  backendLifecycle,
  commandState,
  commandMessage,
  backendErrorMessage,
  playbackState,
  playbackProtocol,
  playbackMessage,
  playbackError,
  onRetry,
}: PlayerOverlayProps) {
  const copy = buildOverlayCopy(
    backendLifecycle,
    commandState,
    commandMessage,
    backendErrorMessage,
    playbackState,
    playbackProtocol,
    playbackMessage,
    playbackError,
  );

  if (!copy) {
    return null;
  }

  const showRetryButton =
    playbackState === "failed" ||
    playbackState === "degraded" ||
    playbackState === "buffering" ||
    backendLifecycle === "reconnecting";

  const toneClasses =
    copy.tone === "error"
      ? "border-rose-500/40 bg-rose-500/12 text-rose-100"
      : copy.tone === "warning"
        ? "border-amber-500/40 bg-amber-500/12 text-amber-50"
        : copy.tone === "info"
          ? "border-sky-500/40 bg-sky-500/12 text-sky-50"
          : "border-slate-500/40 bg-slate-900/70 text-slate-100";

  return (
    <div className="pointer-events-none absolute inset-0 flex items-end justify-start p-4">
      <div
        className={`pointer-events-auto max-w-md rounded-2xl border px-4 py-4 shadow-2xl backdrop-blur transition-all duration-300 ease-out ${toneClasses}`}
      >
        <div className="space-y-2">
          <p className="text-sm font-semibold tracking-[0.14em] uppercase">
            {copy.title}
          </p>
          <p className="text-sm leading-6 text-current/85">{copy.body}</p>
          {showRetryButton ? (
            <button
              type="button"
              onClick={onRetry}
              className="rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/15"
            >
              Retry playback
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
