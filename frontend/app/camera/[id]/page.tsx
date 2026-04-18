import { AppShell } from "@/components/layout/app-shell";
import { CameraDetailScreen } from "@/modules/cameras/components/camera-detail-screen";

interface CameraPageProps {
  params: Promise<{ id: string }>;
}

export default async function CameraPage({ params }: CameraPageProps) {
  const { id } = await params;

  return (
    <AppShell
      title="Camera Detail"
      description="Focused live view for one camera with backend-linked validation and inference controls."
    >
      <CameraDetailScreen cameraId={id} />
    </AppShell>
  );
}
