import type { BackendLifecycleState, PlaybackState } from "@/types/stream";

interface StatusBadgeProps {
  label: string;
  status: BackendLifecycleState | PlaybackState;
}

const STATUS_STYLES: Record<string, string> = {
  active: "border-emerald-400/30 bg-emerald-500/20 text-emerald-300",
  running: "border-emerald-400/30 bg-emerald-500/20 text-emerald-300",
  playing: "border-emerald-400/30 bg-emerald-500/20 text-emerald-300",
  starting: "border-sky-400/30 bg-sky-500/20 text-sky-300",
  loading: "border-sky-400/30 bg-sky-500/20 text-sky-300",
  buffering: "border-sky-400/30 bg-sky-500/20 text-sky-300",
  reconnecting: "border-amber-400/30 bg-amber-500/20 text-amber-300",
  recovering: "border-amber-400/30 bg-amber-500/20 text-amber-300",
  degraded: "border-amber-400/30 bg-amber-500/20 text-amber-300",
  failed: "border-rose-400/30 bg-rose-500/20 text-rose-300",
  error: "border-rose-400/30 bg-rose-500/20 text-rose-300",
  crashed: "border-rose-400/30 bg-rose-500/20 text-rose-300",
  stopped: "border-slate-500/30 bg-slate-500/20 text-slate-300",
  stopping: "border-slate-500/30 bg-slate-500/20 text-slate-300",
  idle: "border-slate-500/30 bg-slate-500/20 text-slate-300",
};

export function StatusBadge({ label, status }: StatusBadgeProps) {
  const visualStyle = STATUS_STYLES[status] ?? STATUS_STYLES.stopped;

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-[0.18em] ${visualStyle}`}
    >
      <span className="size-2 rounded-full bg-current" />
      {label}
    </span>
  );
}
