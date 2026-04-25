import type { InferenceEvent, TrackingEvent, TrackingTrack } from "@/types/realtime";

function inferenceForTrack(cameraId: string, track: TrackingTrack, inference: InferenceEvent[]) {
  return inference.find((item) => {
    if (item.camera_id !== cameraId) {
      return false;
    }
    if (track.persistent_id && item.persistent_id === track.persistent_id) {
      return true;
    }
    return item.local_track_id === track.track_id;
  });
}

function toneClass(level: string | undefined) {
  if (level === "alert") {
    return "border-[var(--danger-strong)] bg-[rgba(168,63,53,0.16)] text-[var(--danger-strong)]";
  }
  if (level === "warning") {
    return "border-[var(--warning-strong)] bg-[rgba(166,114,53,0.16)] text-[var(--warning-strong)]";
  }
  return "border-[var(--success-strong)] bg-[rgba(38,115,86,0.14)] text-[var(--success-strong)]";
}

export function StreamOverlay({
  cameraId,
  tracking,
  inference,
  frameWidth,
  frameHeight,
}: {
  cameraId: string;
  tracking: TrackingEvent | null;
  inference: InferenceEvent[];
  frameWidth: number;
  frameHeight: number;
}) {
  if (!tracking || tracking.camera_id !== cameraId || tracking.tracks.length === 0) {
    return null;
  }

  const cameraInference = inference.filter((item) => item.camera_id === cameraId);

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {tracking.tracks.map((track) => {
        const match = inferenceForTrack(cameraId, track, cameraInference);
        const left = (track.left / frameWidth) * 100;
        const top = (track.top / frameHeight) * 100;
        const width = (track.width / frameWidth) * 100;
        const height = (track.height / frameHeight) * 100;

        return (
          <div
            key={`${cameraId}-${track.track_id}`}
            className={`absolute rounded-[10px] border-2 transition-[left,top,width,height,border-color,background-color] duration-75 ease-linear ${toneClass(match?.alert_level)}`}
            style={{
              left: `${left}%`,
              top: `${top}%`,
              width: `${width}%`,
              height: `${height}%`,
              willChange: "left, top, width, height",
            }}
          >
            <div className="absolute -top-9 left-0 flex min-w-max items-center gap-2 rounded-md bg-[rgba(12,18,24,0.9)] px-2 py-1 text-[11px] font-medium text-white shadow-[0_12px_30px_rgba(0,0,0,0.24)]">
              <span>{track.persistent_id ?? `Track ${track.track_id}`}</span>
              <span className="text-white/70">{Math.round(track.confidence * 100)}%</span>
              <span className={match?.alert_level === "alert" ? "text-[var(--danger-strong)]" : match?.alert_level === "warning" ? "text-[var(--warning-strong)]" : "text-[var(--success-strong)]"}>
                {match?.label ?? "pending"}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
