"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { deleteCamera } from "@/lib/api";
import type { CameraResponse } from "@/types/camera";

interface CameraDetailProps {
  cameraId: string;
  initialCamera: CameraResponse | null;
}

export function CameraDetail({
  cameraId,
  initialCamera,
}: CameraDetailProps) {
  const router = useRouter();
  const camera = initialCamera;

  const handleDelete = async () => {
    const cameraName = camera?.name ?? cameraId;
    if (!window.confirm(`Delete camera "${cameraName}"? This cannot be undone.`)) {
      return;
    }

    try {
      await deleteCamera(cameraId);
      router.push("/dashboard");
      router.refresh();
    } catch {
      // ignore
    }
  };

  return (
    <section className="screen-enter space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-2">
          <Link
            href="/dashboard"
            className="text-sm font-medium text-cyan-300 transition-all duration-300 ease-out hover:text-cyan-200"
          >
            ← Back to dashboard
          </Link>
          <h1 className="text-4xl font-semibold text-slate-50">
            {camera?.name ?? cameraId}
          </h1>
          <p className="max-w-2xl text-base leading-7 text-slate-400">
            Camera details. Stream playback functionality is currently disabled.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void handleDelete()}
            className="rounded-full border border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 transition-all duration-300 ease-out hover:bg-rose-500/20"
          >
            Delete camera
          </button>
        </div>
      </div>

      <div className="grid gap-6">
        <div className="rounded-[28px] border border-white/8 bg-[linear-gradient(160deg,rgba(17,32,42,0.92),rgba(9,18,24,0.92))] p-5 shadow-[0_24px_90px_rgba(0,0,0,0.36)]">
          <h2 className="text-lg font-semibold text-slate-50">Camera Configuration</h2>
          <dl className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm text-slate-300">
            <div className="rounded-2xl border border-white/8 bg-slate-900/60 px-4 py-3">
              <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">Location</dt>
              <dd className="mt-2 font-medium text-slate-100">{camera?.location ?? "N/A"}</dd>
            </div>
            <div className="rounded-2xl border border-white/8 bg-slate-900/60 px-4 py-3">
              <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">Status</dt>
              <dd className="mt-2 font-medium text-slate-100">{camera?.status ?? "Unknown"}</dd>
            </div>
            <div className="rounded-2xl border border-white/8 bg-slate-900/60 px-4 py-3 sm:col-span-2">
              <dt className="text-xs uppercase tracking-[0.18em] text-slate-500">Tags</dt>
              <dd className="mt-2 font-medium text-slate-100">{camera?.tags.join(", ") ?? "None"}</dd>
            </div>
          </dl>
        </div>
      </div>
    </section>
  );
}
