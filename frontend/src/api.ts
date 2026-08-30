import type { LineageResponse, RunDetail, RunSummary, RunsResponse } from "./types";

const configuredBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export function apiUrl(path: string): string {
  return `${configuredBase}${path}`;
}

export function encodedRunPath(runId: string, suffix = ""): string {
  return `/api/runs/${encodeURIComponent(runId)}${suffix}`;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function errorDetail(payload: unknown, fallback: string): string {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "network request failed";
    throw new ApiError(0, message);
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      errorDetail(payload, `request failed with status ${response.status}`),
    );
  }
  return payload as T;
}

export function listRuns(signal?: AbortSignal): Promise<RunsResponse> {
  return requestJson<RunsResponse>("/api/runs", { signal });
}

export function getRunDetail(runId: string, signal?: AbortSignal): Promise<RunDetail> {
  return requestJson<RunDetail>(encodedRunPath(runId), { signal });
}

export function getLineage(runId: string, signal?: AbortSignal): Promise<LineageResponse> {
  return requestJson<LineageResponse>(encodedRunPath(runId, "/lineage"), { signal });
}

export function addRun(path: string): Promise<RunSummary> {
  return requestJson<RunSummary>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
}
