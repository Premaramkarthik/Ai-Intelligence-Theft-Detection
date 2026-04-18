import { AppShell } from "@/components/layout/app-shell";
import { CamerasScreen } from "@/modules/cameras/components/cameras-screen";

export default function CamerasPage() {
  return (
    <AppShell
      title="Camera Management"
      description="Create, validate, inspect, and reconfigure camera streams using the same backend contracts the worker reads."
    >
      <CamerasScreen />
    </AppShell>
  );
}

