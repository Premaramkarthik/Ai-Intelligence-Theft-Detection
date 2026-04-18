import { AppShell } from "@/components/layout/app-shell";
import { CameraForm } from "@/modules/cameras/components/camera-form";

export default function NewCameraPage() {
  return (
    <AppShell
      title="Add Camera"
      description="Register a new RTSP source with validation-ready backend fields and a predictable creation flow."
    >
      <CameraForm />
    </AppShell>
  );
}
