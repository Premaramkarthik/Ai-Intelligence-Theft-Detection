import type { ApiEnvelope } from "@/types/api";

type JsonBody = object | Array<unknown>;

export class ApiError extends Error {
  statusCode: number;
  errorCode: string | null;
  details?: unknown;

  constructor(message: string, statusCode: number, errorCode: string | null = null, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.errorCode = errorCode;
    this.details = details;
  }
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: BodyInit | JsonBody | null;
  timeoutMs?: number;
  retries?: number;
}

const DEFAULT_TIMEOUT_MS = 10_000;

function getBaseUrl(): string {
  const baseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://127.0.0.1:8000";
  return baseUrl.replace(/\/+$/, "");
}

function isJsonBody(body: unknown): body is JsonBody {
  if (body === null || body === undefined) {
    return false;
  }
  if (typeof FormData !== "undefined" && body instanceof FormData) {
    return false;
  }
  if (body instanceof Blob || typeof body === "string" || body instanceof URLSearchParams) {
    return false;
  }
  return typeof body === "object";
}

function sleep(durationMs: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, durationMs);
  });
}

function shouldRetryRequest(method: string, statusCode?: number): boolean {
  const normalizedMethod = method.toUpperCase();
  if (!["GET", "HEAD"].includes(normalizedMethod)) {
    return false;
  }
  if (statusCode === undefined) {
    return true;
  }
  return statusCode === 408 || statusCode === 429 || statusCode >= 500;
}

function combineSignals(controller: AbortController, externalSignal?: AbortSignal): AbortSignal {
  if (!externalSignal) {
    return controller.signal;
  }
  if (externalSignal.aborted) {
    controller.abort();
    return controller.signal;
  }
  externalSignal.addEventListener("abort", () => controller.abort(), { once: true });
  return controller.signal;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? ((await response.json()) as ApiEnvelope<T> | T) : null;

  if (!response.ok) {
    if (payload && typeof payload === "object" && "message" in payload) {
      const envelope = payload as ApiEnvelope<T>;
      throw new ApiError(
        envelope.message || `Request failed with status ${response.status}.`,
        response.status,
        envelope.error_code ?? null,
        payload,
      );
    }
    throw new ApiError(`Request failed with status ${response.status}.`, response.status);
  }

  if (payload && typeof payload === "object" && "status" in payload) {
    const envelope = payload as ApiEnvelope<T>;
    if (envelope.status === "error") {
      throw new ApiError(envelope.message || "The backend returned an error.", response.status, envelope.error_code ?? null, payload);
    }
    if (envelope.data === null) {
      throw new ApiError(envelope.message || "The backend returned no data.", response.status, envelope.error_code ?? null, payload);
    }
    return envelope.data;
  }

  if (payload === null) {
    throw new ApiError("The backend returned an empty response.", response.status);
  }
  return payload as T;
}

async function request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const retries = options.retries ?? (method.toUpperCase() === "GET" ? 2 : 0);

  let attempt = 0;
  while (true) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

    try {
      const headers = new Headers(options.headers);
      let body: BodyInit | null | undefined;
      if (isJsonBody(options.body)) {
        headers.set("Content-Type", "application/json");
        body = JSON.stringify(options.body);
      } else {
        body = options.body as BodyInit | null | undefined;
      }
      const response = await fetch(`${getBaseUrl()}${path}`, {
        ...options,
        method,
        body,
        headers,
        cache: options.cache ?? "no-store",
        signal: combineSignals(controller, options.signal ?? undefined),
      });
      clearTimeout(timeoutId);
      return await parseResponse<T>(response);
    } catch (error) {
      clearTimeout(timeoutId);

      const statusCode = error instanceof ApiError ? error.statusCode : undefined;
      if (attempt >= retries || !shouldRetryRequest(method, statusCode)) {
        if (error instanceof DOMException && error.name === "AbortError") {
          throw new ApiError("The request timed out.", 408);
        }
        throw error;
      }

      attempt += 1;
      await sleep(400 * attempt);
    }
  }
}

export const apiClient = {
  request,
  get: <T>(path: string, options?: Omit<ApiRequestOptions, "method">) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: ApiRequestOptions["body"], options?: Omit<ApiRequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: ApiRequestOptions["body"], options?: Omit<ApiRequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: ApiRequestOptions["body"], options?: Omit<ApiRequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: Omit<ApiRequestOptions, "method">) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
