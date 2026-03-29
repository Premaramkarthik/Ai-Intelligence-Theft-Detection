import { DashboardGrid } from "@/components/DashboardGrid";
import { listCameras } from "@/lib/api";
import type { CameraResponse } from "@/types/stream";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let initialCameras: CameraResponse[] = [];

  try {
    const payload = await listCameras(1, 48);
    initialCameras = payload.items;
  } catch {
    initialCameras = [];
  }

  return <DashboardGrid initialCameras={initialCameras} />;
}
