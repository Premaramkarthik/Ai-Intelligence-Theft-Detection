"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useBackendHealth, useProcessLogs } from "@/modules/pipeline/hooks";
import { useStreamHealth } from "@/modules/streams/hooks";

function toneForStatus(status?: string) {
  if (status === "ok" || status === "healthy") {
    return "success" as const;
  }
  if (status === "warning") {
    return "warning" as const;
  }
  return "danger" as const;
}

export function PipelineOverview() {
  const health = useBackendHealth();
  const streamHealth = useStreamHealth();
  const logs = useProcessLogs(30);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>Backend health</CardTitle>
            <CardDescription>
              Directly backed by `/health` and `/streams/health`.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {health.isLoading ? (
              Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={`health-${index}`} className="h-12 w-full" />
              ))
            ) : health.data ? (
              <>
                {Object.entries(health.data.components).map(([key, component]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-[var(--text-primary)] capitalize">
                        {key.replaceAll("_", " ")}
                      </p>
                      <p className="text-sm text-[var(--text-secondary)]">{component.message}</p>
                    </div>
                    <Badge tone={toneForStatus(component.status)}>{component.status}</Badge>
                  </div>
                ))}
                <div className="flex items-center justify-between rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">Realtime bridge</p>
                    <p className="text-sm text-[var(--text-secondary)]">
                      Kafka-to-websocket bridge health from `/streams/health`.
                    </p>
                  </div>
                  <Badge tone={streamHealth.data?.healthy ? "success" : "danger"}>
                    {streamHealth.data?.healthy ? "healthy" : "error"}
                  </Badge>
                </div>
              </>
            ) : (
              <EmptyState
                title="Health data unavailable"
                description={health.error instanceof Error ? health.error.message : "The backend health endpoint did not return usable data."}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent logs</CardTitle>
            <CardDescription>
              Last lines from the backend health log endpoint.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {logs.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, index) => (
                  <Skeleton key={`log-${index}`} className="h-8 w-full" />
                ))}
              </div>
            ) : logs.data && Object.keys(logs.data).length > 0 ? (
              <div className="space-y-4">
                {Object.entries(logs.data).map(([processName, lines]) => (
                  <div key={processName} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
                      {processName}
                    </p>
                    <div className="max-h-48 space-y-1 overflow-y-auto font-mono text-xs text-[var(--text-secondary)]">
                      {lines.map((line) => (
                        <p key={`${processName}-${line.slice(0, 24)}-${line.length}`}>{line}</p>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No recent logs"
                description="The backend responded without any process log lines."
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

