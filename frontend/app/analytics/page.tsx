import { AppShell } from "@/components/layout/app-shell";
import { PipelineOverview } from "@/modules/pipeline/components/pipeline-overview";

export default function AnalyticsPage() {
  return (
    <AppShell
      title="Operational Analytics"
      description="Live backend health, websocket bridge status, and recent diagnostic logs backed by the currently exposed APIs."
    >
      <PipelineOverview />
    </AppShell>
  );
}
