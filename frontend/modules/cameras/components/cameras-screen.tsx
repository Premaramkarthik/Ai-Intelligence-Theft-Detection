"use client";

import { useState, useTransition } from "react";
import { useSWRConfig } from "swr";
import Link from "next/link";

import { CameraTableSkeleton } from "@/components/skeletons/camera-table-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { deleteCamera, validateCamera } from "@/modules/cameras/api";
import { useCameraList } from "@/modules/cameras/hooks";
import { patchInference } from "@/modules/streams/api";

export function CamerasScreen() {
  const [query, setQuery] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const camerasQuery = useCameraList({ page: 1, page_size: 50, search: query || undefined });
  const { mutate } = useSWRConfig();

  async function refresh() {
    await mutate((key) => Array.isArray(key) && key[0] === "cameras");
  }

  function runAction(action: () => Promise<unknown>, message: string) {
    startTransition(async () => {
      try {
        await action();
        setFeedback(message);
        await refresh();
      } catch (error) {
        setFeedback(error instanceof Error ? error.message : "Request failed.");
      }
    });
  }

  function runDelete(cameraId: string, cameraName: string) {
    if (!window.confirm(`Delete camera "${cameraName}"? This cannot be undone.`)) {
      return;
    }
    runAction(() => deleteCamera(cameraId), `Deleted ${cameraName}.`);
  }

  if (camerasQuery.isLoading) {
    return <CameraTableSkeleton />;
  }

  const cameras = camerasQuery.data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
        <div className="max-w-md">
          <label className="block text-sm font-medium text-[var(--text-secondary)]">
            Search cameras
          </label>
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Front gate, warehouse, loading dock..."
            className="mt-2"
          />
        </div>
        <Button asChild>
          <Link href="/cameras/new">Add camera</Link>
        </Button>
      </div>

      {feedback ? (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3 text-sm text-[var(--text-secondary)]">
          {feedback}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Total cameras</CardDescription>
            <CardTitle className="text-3xl">{cameras.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Active</CardDescription>
            <CardTitle className="text-3xl">{cameras.filter((camera) => camera.status === "active").length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Validation issues</CardDescription>
            <CardTitle className="text-3xl">
              {cameras.filter((camera) => camera.last_validation_status !== "reachable").length}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {camerasQuery.error ? (
        <EmptyState
          title="Camera inventory unavailable"
          description={camerasQuery.error instanceof Error ? camerasQuery.error.message : "Unable to load the camera list."}
        />
      ) : cameras.length === 0 ? (
        <EmptyState
          title="No cameras registered"
          description="Create a camera to begin streaming, tracking, and inference monitoring."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Camera inventory</CardTitle>
            <CardDescription>
              Directly connected to the backend camera CRUD and inference patch endpoints.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {cameras.map((camera) => (
              <div
                key={camera.id}
                className="grid gap-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 xl:grid-cols-[1.4fr_1fr_0.8fr_1.2fr]"
              >
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-[var(--text-primary)]">{camera.name}</p>
                    <Badge tone={camera.status === "active" ? "success" : "neutral"}>
                      {camera.status}
                    </Badge>
                  </div>
                  <p className="text-sm text-[var(--text-secondary)]">
                    {camera.location ?? "No location"} · {camera.rtsp_url_preview}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">{camera.id}</p>
                </div>

                <div className="space-y-2 text-sm">
                  <p className="font-medium text-[var(--text-primary)]">Validation</p>
                  <p className="text-[var(--text-secondary)]">
                    {camera.last_validation_status}
                    {camera.last_validation_message ? ` · ${camera.last_validation_message}` : ""}
                  </p>
                </div>

                <div className="space-y-2 text-sm">
                  <p className="font-medium text-[var(--text-primary)]">Tags</p>
                  <p className="text-[var(--text-secondary)]">
                    {camera.tags.length > 0 ? camera.tags.join(", ") : "No tags"}
                  </p>
                </div>

                <div className="flex flex-wrap items-start gap-2">
                  <Button asChild variant="secondary">
                    <Link href={`/camera/${camera.id}`}>Open</Link>
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={isPending}
                    onClick={() =>
                      runAction(
                        () => validateCamera(camera.id),
                        `Validated ${camera.name}.`,
                      )
                    }
                  >
                    Validate
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={isPending}
                    onClick={() =>
                      runAction(
                        () => patchInference(camera.id, { enabled: true, strategy: "vjepa_probe" }),
                        `Inference switched to VJEPA for ${camera.name}.`,
                      )
                    }
                  >
                    VJEPA
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={isPending}
                    onClick={() =>
                      runAction(
                        () => patchInference(camera.id, { enabled: true, strategy: "cnn_transformer" }),
                        `Inference switched to CNN Transformer for ${camera.name}.`,
                      )
                    }
                  >
                    CNN
                  </Button>
                  <Button
                    variant="danger"
                    disabled={isPending}
                    onClick={() => runDelete(camera.id, camera.name)}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
