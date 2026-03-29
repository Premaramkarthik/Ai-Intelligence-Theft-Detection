import { CameraDetail } from "@/components/CameraDetail";
import { getCamera, getStreamInfo } from "@/lib/api";
import type { CameraResponse, StreamInfoResponse } from "@/types/stream";

export const dynamic = "force-dynamic";

interface CameraPageProps {
  params: Promise<{ id: string }>;
}

export default async function CameraPage({ params }: CameraPageProps) {
  const { id } = await params;

  let initialCamera: CameraResponse | null = null;
  let initialStreamInfo: StreamInfoResponse | null = null;

  try {
    initialCamera = await getCamera(id);
  } catch {
    initialCamera = null;
  }

  try {
    initialStreamInfo = await getStreamInfo(id);
  } catch {
    initialStreamInfo = null;
  }

  return (
    <CameraDetail
      cameraId={id}
      initialCamera={initialCamera}
      initialStreamInfo={initialStreamInfo}
    />
  );
}
