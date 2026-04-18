"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { CameraDetailSkeleton } from "@/components/skeletons/camera-detail-skeleton";
import { StreamCard } from "@/components/video/StreamCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { useCamera } from "@/modules/cameras/hooks";
import { deleteCamera, validateCamera } from "@/modules/cameras/api";
import { patchInference } from "@/modules/streams/api";

export function CameraDetailScreen({ cameraId }: { cameraId: string }) {
  const router = useRouter();
  const cameraQuery = useCamera(cameraId);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  if (cameraQuery.isLoading) {
    return <CameraDetailSkeleton />;
  }

  if (!cameraQuery.data) {
    return (
      <EmptyState
        title="Camera not found"
        description={cameraQuery.error instanceof Error ? cameraQuery.error.message : "The backend did not return a camera record for this id."}
      />
    );
  }

  const camera = cameraQuery.data;

  function runAction(action: () => Promise<unknown>, message: string) {
    startTransition(async () => {
      try {
        await action();
        setFeedback(message);
      } catch (error) {
        setFeedback(error instanceof Error ? error.message : "Request failed.");
      }
    });
  }

  function handleDelete() {
    if (!window.confirm(`Delete camera "${camera.name}"? This cannot be undone.`)) {
      return;
    }
    startTransition(async () => {
      try {
        await deleteCamera(camera.id);
        router.push("/cameras");
        router.refresh();
      } catch (error) {
        setFeedback(error instanceof Error ? error.message : "Delete failed.");
      }
    });
  }

  return (
    <div className="space-y-6">
      {feedback ? (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3 text-sm text-[var(--text-secondary)]">
          {feedback}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.9fr)]">
        <StreamCard camera={camera} />

        <Card>
          <CardHeader>
            <CardTitle>Camera metadata</CardTitle>
            <CardDescription>Backend configuration, validation, and quick actions.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
                <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">Location</p>
                <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">{camera.location ?? "No location"}</p>
              </div>
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
                <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">Status</p>
                <div className="mt-2">
                  <Badge tone={camera.status === "active" ? "success" : "neutral"}>{camera.status}</Badge>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
              <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">RTSP preview</p>
              <p className="mt-2 break-all text-sm text-[var(--text-secondary)]">{camera.rtsp_url_preview}</p>
            </div>

            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
              <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">Validation</p>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                {camera.last_validation_status}
                {camera.last_validation_message ? ` · ${camera.last_validation_message}` : ""}
              </p>
            </div>

            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3">
              <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">Metadata</p>
              <pre className="mt-2 overflow-x-auto text-xs text-[var(--text-secondary)]">
{JSON.stringify(camera.metadata, null, 2)}
              </pre>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" disabled={isPending} onClick={() => runAction(() => validateCamera(camera.id), `Validated ${camera.name}.`)}>
                Validate
              </Button>
              <Button variant="secondary" disabled={isPending} onClick={() => runAction(() => patchInference(camera.id, { enabled: true, strategy: "vjepa_probe" }), `VJEPA enabled for ${camera.name}.`)}>
                VJEPA
              </Button>
              <Button variant="secondary" disabled={isPending} onClick={() => runAction(() => patchInference(camera.id, { enabled: true, strategy: "cnn_transformer" }), `CNN enabled for ${camera.name}.`)}>
                CNN
              </Button>
              <Button variant="danger" disabled={isPending} onClick={handleDelete}>
                Delete
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
