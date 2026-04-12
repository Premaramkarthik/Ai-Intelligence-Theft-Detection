"use client";

import type { InferenceEvent } from "@/types/stream";

interface InferenceDashboardPanelProps {
  activeEvents: InferenceEvent[];
  recentAlerts: InferenceEvent[];
  primaryAlertLabel: string;
}

function formatScore(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function InferenceDashboardPanel({
  activeEvents,
  recentAlerts,
  primaryAlertLabel,
}: InferenceDashboardPanelProps) {
  const activeAlertEvents = activeEvents.filter((event) => event.alert_level !== "normal");
  const averageScore =
    activeEvents.length > 0
      ? activeEvents.reduce((sum, event) => sum + event.score, 0) / activeEvents.length
      : 0;
  const labelCounts = activeEvents.reduce<Record<string, number>>((accumulator, event) => {
    accumulator[event.label] = (accumulator[event.label] ?? 0) + 1;
    return accumulator;
  }, {});
  const maxCount = Math.max(...Object.values(labelCounts), 1);

  return (
    <section className="rounded-[32px] border border-white/8 bg-[linear-gradient(160deg,rgba(13,24,34,0.95),rgba(4,10,18,0.92))] p-6 shadow-[0_30px_120px_rgba(0,0,0,0.38)]">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.24em] text-cyan-300">
            Behavioral inference
          </p>
          <h2 className="text-2xl font-semibold text-slate-50">
            Temporal event telemetry
          </h2>
          <p className="max-w-2xl text-sm leading-6 text-slate-400">
            Live inference events received over the stream websocket, grouped by
            tracked identity and model label.
          </p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-300">
          Primary alert label:{" "}
          <span className="font-semibold text-rose-300">{primaryAlertLabel}</span>
        </div>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-3xl border border-white/8 bg-white/[0.03] p-5">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Active tracks</p>
          <p className="mt-3 text-4xl font-semibold text-slate-50">{activeEvents.length}</p>
        </div>
        <div className="rounded-3xl border border-rose-400/20 bg-rose-500/10 p-5">
          <p className="text-xs uppercase tracking-[0.18em] text-rose-200/80">Active alerts</p>
          <p className="mt-3 text-4xl font-semibold text-rose-50">{activeAlertEvents.length}</p>
        </div>
        <div className="rounded-3xl border border-cyan-400/20 bg-cyan-500/10 p-5">
          <p className="text-xs uppercase tracking-[0.18em] text-cyan-100/80">
            Average score
          </p>
          <p className="mt-3 text-4xl font-semibold text-cyan-50">
            {formatScore(averageScore)}
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="space-y-4 rounded-3xl border border-white/8 bg-white/[0.03] p-5">
          <h3 className="text-lg font-semibold text-slate-50">Label distribution</h3>
          {Object.keys(labelCounts).length === 0 ? (
            <p className="text-sm text-slate-500">No active inference tracks yet.</p>
          ) : (
            <div className="space-y-3">
              {Object.entries(labelCounts).map(([label, count]) => (
                <div key={label} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-slate-200">{label}</span>
                    <span className="text-slate-400">{count}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-900/80">
                    <div
                      className={`h-full rounded-full ${
                        label === "normal"
                          ? "bg-emerald-400"
                          : label === primaryAlertLabel
                            ? "bg-rose-400"
                            : "bg-amber-400"
                      }`}
                      style={{ width: `${(count / maxCount) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="overflow-hidden rounded-3xl border border-white/8 bg-white/[0.03]">
          <div className="border-b border-white/8 px-5 py-4">
            <h3 className="text-lg font-semibold text-slate-50">Recent alert feed</h3>
          </div>
          <div className="max-h-96 overflow-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-950/60 text-slate-400">
                <tr>
                  <th className="px-5 py-3 font-medium">Camera</th>
                  <th className="px-5 py-3 font-medium">Track</th>
                  <th className="px-5 py-3 font-medium">Label</th>
                  <th className="px-5 py-3 font-medium">Score</th>
                  <th className="px-5 py-3 font-medium">Model</th>
                </tr>
              </thead>
              <tbody>
                {recentAlerts.length === 0 ? (
                  <tr>
                    <td
                      className="px-5 py-6 text-slate-500"
                      colSpan={5}
                    >
                      No non-normal inference events have been received yet.
                    </td>
                  </tr>
                ) : (
                  recentAlerts.map((event, index) => (
                    <tr
                      key={`${event.camera_id}-${event.persistent_id}-${event.emitted_at}-${index}`}
                      className="border-t border-white/5 text-slate-200"
                    >
                      <td className="px-5 py-3">{event.camera_id}</td>
                      <td className="px-5 py-3">{event.local_track_id}</td>
                      <td className="px-5 py-3">{event.label}</td>
                      <td className="px-5 py-3">{formatScore(event.score)}</td>
                      <td className="px-5 py-3">{event.model_name}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-3xl border border-white/8 bg-white/[0.03]">
        <div className="border-b border-white/8 px-5 py-4">
          <h3 className="text-lg font-semibold text-slate-50">Active tracks</h3>
        </div>
        <div className="max-h-[28rem] overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-950/60 text-slate-400">
              <tr>
                <th className="px-5 py-3 font-medium">Camera</th>
                <th className="px-5 py-3 font-medium">Track</th>
                <th className="px-5 py-3 font-medium">Persistent ID</th>
                <th className="px-5 py-3 font-medium">Label</th>
                <th className="px-5 py-3 font-medium">Score</th>
                <th className="px-5 py-3 font-medium">Strategy</th>
              </tr>
            </thead>
            <tbody>
              {activeEvents.length === 0 ? (
                <tr>
                  <td
                    className="px-5 py-6 text-slate-500"
                    colSpan={6}
                  >
                    Waiting for live inference events.
                  </td>
                </tr>
              ) : (
                activeEvents.map((event) => (
                  <tr
                    key={`${event.camera_id}:${event.persistent_id}:${event.local_track_id}`}
                    className="border-t border-white/5 text-slate-200"
                  >
                    <td className="px-5 py-3">{event.camera_id}</td>
                    <td className="px-5 py-3">{event.local_track_id}</td>
                    <td className="px-5 py-3 font-mono text-xs text-slate-400">
                      {event.persistent_id}
                    </td>
                    <td className="px-5 py-3">{event.label}</td>
                    <td className="px-5 py-3">{formatScore(event.score)}</td>
                    <td className="px-5 py-3">{event.strategy}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
