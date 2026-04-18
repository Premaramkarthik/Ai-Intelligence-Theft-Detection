import { CameraDetail } from "@/components/CameraDetail";
import { getCamera } from "@/lib/api";
import type { CameraResponse } from "@/types/camera";

export const dynamic = "force-dynamic";

interface CameraPageProps {
  params: Promise<{ id: string }>;
}

export default async function CameraPage({ params }: CameraPageProps) {
  const { id } = await params;

  let initialCamera: CameraResponse | null = null;

  try {
    initialCamera = await getCamera(id);
  } catch {
    initialCamera = null;
  }

  return (
    <CameraDetail
      cameraId={id}
      initialCamera={initialCamera}
    />
  );
}
