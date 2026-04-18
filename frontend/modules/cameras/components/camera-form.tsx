"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/services/apiClient";
import { createCamera } from "@/modules/cameras/api";
import type { CreateCameraRequest } from "@/types/camera";

type SourceMode = "direct" | "components";

interface CameraDraft {
  name: string;
  location: string;
  host: string;
  port: string;
  username: string;
  password: string;
  path: string;
  directRtspUrl: string;
  transport: "tcp" | "udp";
  status: "active" | "inactive" | "error";
  tags: string;
  metadata: string;
}

const INITIAL_DRAFT: CameraDraft = {
  name: "",
  location: "",
  host: "",
  port: "554",
  username: "",
  password: "",
  path: "",
  directRtspUrl: "",
  transport: "tcp",
  status: "active",
  tags: "",
  metadata: "{\n  \"mediamtx_stream_name\": \"\"\n}",
};

function parseTags(rawTags: string) {
  return rawTags
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function validateDraft(sourceMode: SourceMode, draft: CameraDraft): string | null {
  if (draft.name.trim().length < 2) {
    return "Camera name must be at least 2 characters.";
  }
  if (sourceMode === "direct" && !draft.directRtspUrl.trim()) {
    return "Provide a direct RTSP URL.";
  }
  if (sourceMode === "components" && (!draft.host.trim() || !draft.path.trim())) {
    return "Provide both host and path when using component mode.";
  }
  return null;
}

export function CameraForm() {
  const router = useRouter();
  const [sourceMode, setSourceMode] = useState<SourceMode>("direct");
  const [draft, setDraft] = useState<CameraDraft>(INITIAL_DRAFT);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function updateField<K extends keyof CameraDraft>(field: K, value: CameraDraft[K]) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) {
      return;
    }

    const validationError = validateDraft(sourceMode, draft);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    let metadata: Record<string, unknown>;
    try {
      metadata = draft.metadata.trim() ? (JSON.parse(draft.metadata) as Record<string, unknown>) : {};
    } catch {
      setErrorMessage("Metadata must be valid JSON.");
      return;
    }

    const payload: CreateCameraRequest = {
      name: draft.name.trim(),
      location: draft.location.trim() || null,
      host: sourceMode === "components" ? draft.host.trim() || null : null,
      port: Number.parseInt(draft.port.trim(), 10) || 554,
      username: draft.username.trim() || null,
      password: draft.password.trim() || null,
      path: sourceMode === "components" ? draft.path.trim() || null : null,
      direct_rtsp_url: sourceMode === "direct" ? draft.directRtspUrl.trim() || null : null,
      transport: draft.transport,
      status: draft.status,
      metadata,
      tags: parseTags(draft.tags),
    };

    try {
      setIsSubmitting(true);
      setErrorMessage(null);
      const camera = await createCamera(payload);
      router.push(`/camera/${camera.id}`);
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError || error instanceof Error) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Camera creation failed.");
      }
      setIsSubmitting(false);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]">
      <Card>
        <CardHeader>
          <CardTitle>Create camera</CardTitle>
          <CardDescription>
            This form maps directly to the backend camera creation contract.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-sm font-medium text-[var(--text-secondary)]">Camera name</span>
                <Input value={draft.name} onChange={(event) => updateField("name", event.target.value)} placeholder="Front gate" />
              </label>
              <label className="space-y-2">
                <span className="text-sm font-medium text-[var(--text-secondary)]">Location</span>
                <Input value={draft.location} onChange={(event) => updateField("location", event.target.value)} placeholder="Warehouse" />
              </label>
            </div>

            <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">Source mode</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button type="button" variant={sourceMode === "direct" ? "primary" : "secondary"} onClick={() => setSourceMode("direct")}>
                  Direct RTSP URL
                </Button>
                <Button type="button" variant={sourceMode === "components" ? "primary" : "secondary"} onClick={() => setSourceMode("components")}>
                  Host + path
                </Button>
              </div>
            </div>

            {sourceMode === "direct" ? (
              <label className="space-y-2">
                <span className="text-sm font-medium text-[var(--text-secondary)]">Direct RTSP URL</span>
                <Input value={draft.directRtspUrl} onChange={(event) => updateField("directRtspUrl", event.target.value)} placeholder="rtsp://user:pass@host:554/stream" />
              </label>
            ) : (
              <div className="grid gap-4 md:grid-cols-[1fr_120px_1fr]">
                <label className="space-y-2">
                  <span className="text-sm font-medium text-[var(--text-secondary)]">Host</span>
                  <Input value={draft.host} onChange={(event) => updateField("host", event.target.value)} placeholder="192.168.1.20" />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-[var(--text-secondary)]">Port</span>
                  <Input value={draft.port} onChange={(event) => updateField("port", event.target.value)} placeholder="554" />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-[var(--text-secondary)]">Path</span>
                  <Input value={draft.path} onChange={(event) => updateField("path", event.target.value)} placeholder="/stream1" />
                </label>
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-sm font-medium text-[var(--text-secondary)]">Username</span>
                <Input value={draft.username} onChange={(event) => updateField("username", event.target.value)} placeholder="Optional" />
              </label>
              <label className="space-y-2">
                <span className="text-sm font-medium text-[var(--text-secondary)]">Password</span>
                <Input type="password" value={draft.password} onChange={(event) => updateField("password", event.target.value)} placeholder="Optional" />
              </label>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <label className="space-y-2">
                <span className="text-sm font-medium text-[var(--text-secondary)]">Transport</span>
                <select
                  value={draft.transport}
                  onChange={(event) => updateField("transport", event.target.value as CameraDraft["transport"])}
                  className="h-11 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--surface-1)] px-3 text-sm text-[var(--text-primary)] outline-none"
                >
                  <option value="tcp">TCP</option>
                  <option value="udp">UDP</option>
                </select>
              </label>
              <label className="space-y-2">
                <span className="text-sm font-medium text-[var(--text-secondary)]">Initial status</span>
                <select
                  value={draft.status}
                  onChange={(event) => updateField("status", event.target.value as CameraDraft["status"])}
                  className="h-11 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--surface-1)] px-3 text-sm text-[var(--text-primary)] outline-none"
                >
                  <option value="inactive">Inactive</option>
                  <option value="active">Active</option>
                  <option value="error">Error</option>
                </select>
              </label>
              <label className="space-y-2">
                <span className="text-sm font-medium text-[var(--text-secondary)]">Tags</span>
                <Input value={draft.tags} onChange={(event) => updateField("tags", event.target.value)} placeholder="front-gate, entry" />
              </label>
            </div>

            <label className="space-y-2">
              <span className="text-sm font-medium text-[var(--text-secondary)]">Metadata JSON</span>
              <Textarea value={draft.metadata} onChange={(event) => updateField("metadata", event.target.value)} />
            </label>

            {errorMessage ? (
              <div className="rounded-xl border border-[var(--danger-soft)] bg-[rgba(168,63,53,0.10)] px-4 py-3 text-sm text-[var(--danger-strong)]">
                {errorMessage}
              </div>
            ) : null}

            <div className="flex flex-wrap justify-end gap-3">
              <Button asChild variant="secondary">
                <Link href="/cameras">Cancel</Link>
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Creating..." : "Create camera"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Backend contract preview</CardTitle>
          <CardDescription>
            Review the payload that will be sent to the FastAPI backend.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 text-xs text-[var(--text-secondary)]">
{JSON.stringify(
  {
    name: draft.name || "Front gate",
    location: draft.location || "Warehouse",
    host: sourceMode === "components" ? draft.host || null : null,
    port: Number.parseInt(draft.port, 10) || 554,
    username: draft.username || null,
    password: draft.password ? "***" : null,
    path: sourceMode === "components" ? draft.path || null : null,
    direct_rtsp_url: sourceMode === "direct" ? draft.directRtspUrl || null : null,
    transport: draft.transport,
    status: draft.status,
    tags: parseTags(draft.tags),
  },
  null,
  2,
)}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}

