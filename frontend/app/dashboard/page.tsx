import { AppShell } from "@/components/layout/app-shell";
import { DashboardScreen } from "@/modules/streams/components/dashboard-screen";

export default function DashboardPage() {
  return (
    <AppShell
      title="Live Dashboard"
      description="Real-time camera streams with tracking overlays, inference labels, and resilient websocket-driven updates."
    >
      <DashboardScreen />
    </AppShell>
  );
}

