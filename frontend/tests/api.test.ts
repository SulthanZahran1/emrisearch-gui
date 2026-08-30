import { afterEach, describe, expect, it, vi } from "vitest";
import { addRun, encodedRunPath, getLineage, getRunDetail, listRuns, ApiError } from "../src/api";
import { jsonResponse, makeSummary } from "./fixtures";

function installFetch() {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("API URL and wire contracts", () => {
  it("encodes nested and space-containing run ids as one path segment", async () => {
    const fetchMock = installFetch();
    fetchMock.mockImplementation(() => jsonResponse({ summary: { id: "stage 01/replica a" } }));

    expect(encodedRunPath("stage 01/replica a")).toBe("/api/runs/stage%2001%2Freplica%20a");
    await getRunDetail("stage 01/replica a");
    await getLineage("stage 01/replica a");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/runs/stage%2001%2Freplica%20a",
      "/api/runs/stage%2001%2Freplica%20a/lineage",
    ]);
  });

  it("surfaces a JSON detail error with its HTTP status", async () => {
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(jsonResponse({ detail: "run not found: missing id" }, 404));

    const result = listRuns();

    await expect(result).rejects.toBeInstanceOf(ApiError);
    await expect(result).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      detail: "run not found: missing id",
    });
  });

  it("uses a status fallback when an error response is not JSON", async () => {
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(new Response("gateway unavailable", { status: 502 }));

    await expect(listRuns()).rejects.toMatchObject({
      status: 502,
      detail: "request failed with status 502",
    });
  });

  it("posts the exact server-side path as JSON and accepts a created summary", async () => {
    const fetchMock = installFetch();
    const registered = makeSummary({ id: "new run" });
    fetchMock.mockResolvedValue(jsonResponse(registered, 201));

    await expect(addRun("/scratch/emri/run with spaces")).resolves.toEqual(registered);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runs");
    expect(init).toMatchObject({
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
    });
    expect(JSON.parse(init.body as string)).toEqual({ path: "/scratch/emri/run with spaces" });
  });
});
