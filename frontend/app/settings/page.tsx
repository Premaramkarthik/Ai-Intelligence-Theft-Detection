import { AppShell } from "@/components/layout/app-shell";
import { PipelineOverview } from "@/modules/pipeline/components/pipeline-overview";

export default function SettingsPage() {
  return (
    <AppShell
      title="System Status"
      description="Operational diagnostics sourced from backend health and process log endpoints."
    >
      <PipelineOverview />
    </AppShell>
  );
}
