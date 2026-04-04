"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { BackendApiError, createCamera } from "@/lib/api";
import { useStreamStore } from "@/store/streamStore";

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
  status: "inactive",
  tags: "",
  metadata: '{\n  "mediamtx_stream_name": ""\n}',
};

/**
 * Parse a comma-separated tag string into the backend contract format.
 */
function parseTags(rawTags: string): string[] {
  return rawTags
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

/**
 * Build a frontend-friendly validation error before the request is sent.
 */
function validateDraft(sourceMode: SourceMode, draft: CameraDraft): string | null {
  if (draft.name.trim().length < 2) {
    return "Camera name must be at least 2 characters.";
  }

  if (sourceMode === "direct" && !draft.directRtspUrl.trim()) {
    return "Provide a direct RTSP URL.";
  }

  if (sourceMode === "components") {
    if (!draft.host.trim()) {
      return "Provide the camera host.";
    }
    if (!draft.path.trim()) {
      return "Provide the stream path.";
    }
  }

  return null;
}

/**
 * Render the create-camera screen backed by the FastAPI contract.
 */
export function CreateCameraForm() {
  const router = useRouter();
  const upsertCamera = useStreamStore((state) => state.upsertCamera);
  const [sourceMode, setSourceMode] = useState<SourceMode>("direct");
  const [draft, setDraft] = useState<CameraDraft>(INITIAL_DRAFT);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const previewUrl = useMemo(() => {
    if (sourceMode === "direct") {
      return draft.directRtspUrl.trim() || "rtsp://192.168.1.2:8080/h264_ulaw.sdp";
    }

    const host = draft.host.trim() || "192.168.1.2";
    const port = draft.port.trim() || "554";
    const path = draft.path.trim() || "/h264_ulaw.sdp";
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    return `rtsp://${host}:${port}${normalizedPath}`;
  }, [draft.directRtspUrl, draft.host, draft.path, draft.port, sourceMode]);

  const updateField = <K extends keyof CameraDraft>(field: K, value: CameraDraft[K]) => {
    setDraft((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
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
      metadata = draft.metadata.trim()
        ? (JSON.parse(draft.metadata) as Record<string, unknown>)
        : {};
    } catch {
      setErrorMessage("Metadata must be valid JSON.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const camera = await createCamera({
        name: draft.name.trim(),
        location: draft.location.trim() || null,
        host: sourceMode === "components" ? draft.host.trim() || null : null,
        port: Number.parseInt(draft.port.trim(), 10) || 554,
        username: draft.username.trim() || null,
        password: draft.password.trim() || null,
        path: sourceMode === "components" ? draft.path.trim() || null : null,
        direct_rtsp_url:
          sourceMode === "direct" ? draft.directRtspUrl.trim() || null : null,
        transport: draft.transport,
        status: draft.status,
        metadata,
        tags: parseTags(draft.tags),
      });
      upsertCamera(camera);
      router.replace(`/camera/${camera.id}`);
      router.refresh();
    } catch (error) {
      if (error instanceof BackendApiError) {
        setErrorMessage(error.message);
      } else if (error instanceof Error) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Camera creation failed.");
      }
      setIsSubmitting(false);
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
            Add camera
          </h1>
          <p className="max-w-2xl text-base leading-7 text-slate-300">
            Register a new RTSP source using the same contract the backend
            validates before it allows stream startup, so bad camera URLs are
            caught early instead of failing silently in the player.
          </p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.9fr)]">
        <form
          onSubmit={onSubmit}
          className="space-y-6 rounded-[28px] border border-white/8 bg-[linear-gradient(160deg,rgba(17,32,42,0.92),rgba(9,18,24,0.92))] p-6 shadow-[0_24px_90px_rgba(0,0,0,0.36)]"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-200">Camera name</span>
              <input
                value={draft.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder="Front gate"
                className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-200">Location</span>
              <input
                value={draft.location}
                onChange={(event) => updateField("location", event.target.value)}
                placeholder="Building A"
                className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
              />
            </label>
          </div>

          <div className="rounded-[24px] border border-white/6 bg-slate-950/55 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Source mode
            </p>
            <div className="mt-3 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => setSourceMode("direct")}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition-all duration-300 ease-out ${
                  sourceMode === "direct"
                    ? "bg-cyan-300 text-slate-950"
                    : "border border-white/10 bg-slate-900 text-slate-100 hover:bg-slate-800"
                }`}
              >
                Direct RTSP URL
              </button>
              <button
                type="button"
                onClick={() => setSourceMode("components")}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition-all duration-300 ease-out ${
                  sourceMode === "components"
                    ? "bg-cyan-300 text-slate-950"
                    : "border border-white/10 bg-slate-900 text-slate-100 hover:bg-slate-800"
                }`}
              >
                Host + path
              </button>
            </div>
          </div>

          {sourceMode === "direct" ? (
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-200">Direct RTSP URL</span>
              <input
                value={draft.directRtspUrl}
                onChange={(event) => updateField("directRtspUrl", event.target.value)}
                placeholder="rtsp://192.168.1.2:8080/h264_ulaw.sdp"
                className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
              />
            </label>
          ) : (
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="space-y-2 sm:col-span-2">
                <span className="text-sm font-medium text-slate-200">Host</span>
                <input
                  value={draft.host}
                  onChange={(event) => updateField("host", event.target.value)}
                  placeholder="192.168.1.2"
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
                />
              </label>
              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-200">Port</span>
                <input
                  value={draft.port}
                  onChange={(event) => updateField("port", event.target.value)}
                  placeholder="554"
                  inputMode="numeric"
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
                />
              </label>
              <label className="space-y-2 sm:col-span-3">
                <span className="text-sm font-medium text-slate-200">Path</span>
                <input
                  value={draft.path}
                  onChange={(event) => updateField("path", event.target.value)}
                  placeholder="/h264_ulaw.sdp"
                  className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
                />
              </label>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-200">Username</span>
              <input
                value={draft.username}
                onChange={(event) => updateField("username", event.target.value)}
                placeholder="Optional"
                className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-200">Password</span>
              <input
                type="password"
                value={draft.password}
                onChange={(event) => updateField("password", event.target.value)}
                placeholder="Optional"
                className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
              />
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-200">Transport</span>
              <select
                value={draft.transport}
                onChange={(event) =>
                  updateField("transport", event.target.value as CameraDraft["transport"])
                }
                className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out focus:border-cyan-400/40"
              >
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
              </select>
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-200">Status</span>
              <select
                value={draft.status}
                onChange={(event) =>
                  updateField("status", event.target.value as CameraDraft["status"])
                }
                className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out focus:border-cyan-400/40"
              >
                <option value="inactive">Inactive</option>
                <option value="active">Active</option>
                <option value="error">Error</option>
              </select>
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-200">Tags</span>
              <input
                value={draft.tags}
                onChange={(event) => updateField("tags", event.target.value)}
                placeholder="front-gate, perimeter"
                className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
              />
            </label>
          </div>

          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-200">Metadata (JSON)</span>
            <textarea
              value={draft.metadata}
              onChange={(event) => updateField("metadata", event.target.value)}
              rows={8}
              className="w-full rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition-all duration-300 ease-out placeholder:text-slate-500 focus:border-cyan-400/40"
            />
          </label>

          {errorMessage ? (
            <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100 transition-all duration-300 ease-out">
              {errorMessage}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-full bg-amber-300 px-5 py-3 text-sm font-semibold text-slate-950 transition-all duration-300 ease-out hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? "Creating camera..." : "Create camera"}
            </button>
            <Link
              href="/dashboard"
              className="rounded-full border border-white/10 px-5 py-3 text-sm font-semibold text-slate-100 transition-all duration-300 ease-out hover:border-white/20 hover:bg-white/5"
            >
              Cancel
            </Link>
          </div>
        </form>

        <aside className="space-y-5">
          <div className="rounded-[28px] border border-white/8 bg-[linear-gradient(160deg,rgba(17,32,42,0.92),rgba(9,18,24,0.92))] p-5">
            <h2 className="text-lg font-semibold text-slate-50">Preview</h2>
            <div className="mt-4 rounded-2xl border border-white/6 bg-slate-950/55 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Source URL preview
              </p>
              <p className="mt-2 break-all text-sm text-slate-100">{previewUrl}</p>
            </div>
            <div className="mt-4 rounded-2xl border border-white/6 bg-slate-950/55 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Backend rules
              </p>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                <li>Provide either a direct RTSP URL or a host with path.</li>
                <li>TCP is the safest default transport for MediaMTX ingestion.</li>
                <li>Metadata is stored as JSON and can include `mediamtx_stream_name`.</li>
              </ul>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
