import { buildGrafanaDashboardUrl, buildPrometheusTargetsUrl } from "@/lib/observability";
import type { WorkerStateResponse } from "@/types/stream";

interface WorkerMetricsPanelProps {
  worker: WorkerStateResponse | null;
  compact?: boolean;
}

/**
 * Format worker-side numeric metrics for compact frontend presentation.
 */
function formatMetric(value: number, suffix = ""): string {
  if (!Number.isFinite(value)) {
    return `0${suffix}`;
  }

  const normalized =
    Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(1).replace(/\.0$/, "");
  return `${normalized}${suffix}`;
}

/**
 * Surface backend worker and observability links without leaking implementation details.
 */
export function WorkerMetricsPanel({
  worker,
  compact = false,
}: WorkerMetricsPanelProps) {
  const metrics = [
    {
      label: "FPS",
      value: formatMetric(worker?.current_fps ?? 0),
    },
    {
      label: "Queue",
      value: formatMetric(worker?.queue_latency_ms ?? 0, " ms"),
    },
    {
      label: "Decode",
      value: formatMetric(worker?.decode_time_ms ?? 0, " ms"),
    },
    {
      label: "Drops",
      value: formatMetric(worker?.dropped_frames ?? 0),
    },
    {
      label: "Reconnects",
      value: formatMetric(worker?.reconnect_attempts ?? 0),
    },
    {
      label: "Samples",
      value: formatMetric(worker?.sampled_frames ?? 0),
    },
  ];

  return (
    <section className="space-y-4 rounded-[28px] border border-white/8 bg-[linear-gradient(160deg,rgba(17,32,42,0.92),rgba(9,18,24,0.92))] p-5 transition-all duration-300 ease-out">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-slate-50">
            Stream observability
          </h2>
          <p className="text-sm leading-6 text-slate-400">
            Backend worker metrics update with the active stream contract so the
            operator can verify health without leaving the player.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href={buildGrafanaDashboardUrl()}
            target="_blank"
            rel="noreferrer"
            className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-500/20"
          >
            Open Grafana
          </a>
          <a
            href={buildPrometheusTargetsUrl()}
            target="_blank"
            rel="noreferrer"
            className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-100 transition hover:border-white/20 hover:bg-white/5"
          >
            Prometheus targets
          </a>
        </div>
      </div>

      <div
        className={`grid gap-3 ${
          compact ? "grid-cols-2 xl:grid-cols-3" : "grid-cols-2 lg:grid-cols-3"
        }`}
      >
        {metrics.map((metric) => (
          <div
            key={metric.label}
            className="rounded-2xl border border-white/6 bg-slate-950/55 px-4 py-4"
          >
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
              {metric.label}
            </p>
            <p className="mt-2 text-xl font-semibold text-slate-50">
              {metric.value}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
