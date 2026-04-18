import type { CameraStatus } from "@/types/camera";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function getApiBaseUrl(): string {
  return trimTrailingSlash(
    process.env.NEXT_PUBLIC_API_BASE_URL ??
      process.env.NEXT_PUBLIC_API_URL ??
      DEFAULT_API_BASE_URL,
  );
}

export function getWebSocketUrl(): string {
  const configured =
    process.env.NEXT_PUBLIC_WS_BASE_URL ??
    process.env.NEXT_PUBLIC_WS_URL;

  if (configured) {
    const normalized = configured.includes("/streams/ws/updates")
      ? configured
      : `${trimTrailingSlash(configured)}/streams/ws/updates`;
    return normalized;
  }

  const baseUrl = getApiBaseUrl();
  const websocketBase = baseUrl.startsWith("https://")
    ? baseUrl.replace("https://", "wss://")
    : baseUrl.replace("http://", "ws://");
  return `${websocketBase}/streams/ws/updates`;
}

function withQuery(path: string, params: Record<string, string | number | boolean | undefined | null>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    query.set(key, String(value));
  }
  const serialized = query.toString();
  return serialized ? `${path}?${serialized}` : path;
}

export const endpoints = {
  cameras: {
    list: (params?: { page?: number; page_size?: number; search?: string; status?: CameraStatus | "all" }) =>
      withQuery("/cameras", {
        page: params?.page ?? 1,
        page_size: params?.page_size ?? 24,
        search: params?.search,
        status: params?.status === "all" ? undefined : params?.status,
      }),
    create: "/cameras",
    detail: (cameraId: string) => `/cameras/${encodeURIComponent(cameraId)}`,
    validate: (cameraId: string) => `/cameras/${encodeURIComponent(cameraId)}/validate`,
  },
  streams: {
    health: "/streams/health",
    inference: (cameraId: string) => `/streams/${encodeURIComponent(cameraId)}/inference`,
    updates: "/streams/ws/updates",
  },
  health: {
    root: "/health",
    db: "/health/db",
    logs: (lines = 60) => withQuery("/health/logs", { lines }),
  },
};

