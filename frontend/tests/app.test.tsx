import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import type { RunSummary } from "../src/types";
import { jsonResponse, makeDetail, makeLineage, makeSummary } from "./fixtures";

function installFetch(
  handler: (url: string, init?: RequestInit) => Response | Promise<Response>,
) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(handler(String(input), init)),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function installRunFetch(
  runs: RunSummary[],
  selectedId = runs[0]?.id ?? "stage_00",
) {
  const detail = makeDetail(selectedId);
  return installFetch((url) => {
    if (url === "/api/runs") return jsonResponse({ runs, warnings: [] });
    if (url.includes("/lineage")) return jsonResponse({ chain: makeLineage([selectedId]) });
    if (url.includes("/api/runs/")) return jsonResponse(detail);
    throw new Error(`unexpected request: ${url}`);
  });
}

function selectHash(runId: string) {
  window.location.hash = `#/run/${encodeURIComponent(runId)}`;
}

describe("application states and run rail", () => {
  it("shows a loading skeleton while the run list is pending", () => {
    installFetch(() => new Promise<Response>(() => undefined));

    render(<App />);

    expect(screen.getByText("Loading runs")).toBeInTheDocument();
    expect(screen.getByLabelText("Loading discovered runs")).toBeInTheDocument();
  });

  it("renders the API error state with the backend error text", async () => {
    installFetch(() => jsonResponse({ detail: "backend unavailable" }, 503));

    render(<App />);

    expect(await screen.findByRole("heading", { name: "API unavailable" })).toBeInTheDocument();
    expect(screen.getAllByText("backend unavailable")).toHaveLength(2);
  });

  it("renders the empty state without inventing sample runs", async () => {
    installFetch(() => jsonResponse({ runs: [], warnings: [] }));

    render(<App />);

    expect(await screen.findByRole("heading", { name: "No runs discovered" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /stage_/ })).not.toBeInTheDocument();
  });

  it("renders snake_case run metadata and groups a chain in the rail", async () => {
    const runs = [
      makeSummary({ id: "stage_00", from_run: null, kind: "internal_lhs", ndim: 4 }),
      makeSummary({ id: "stage_01", from_run: "stage_00", kind: "from_run", ndim: 4 }),
      makeSummary({ id: "stage_02", from_run: "stage_01", kind: "from_run", ndim: 4 }),
      makeSummary({ id: "independent", from_run: null, kind: "internal_lhs", ndim: null }),
    ];
    installRunFetch(runs);

    render(<App />);

    expect(await screen.findByText("chain: stage_00")).toBeInTheDocument();
    expect(screen.getByText("chain: independent")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /stage_01/ })).toHaveTextContent("from run");
    expect(screen.getByRole("button", { name: /independent/ })).toHaveTextContent("unset");
    expect(screen.getAllByText("f_pure").length).toBeGreaterThan(0);
  });

  it("keeps a nested and space-containing id in the hash route and requests it encoded", async () => {
    const id = "stage 01/replica a";
    const runs = [makeSummary({ id, path: `/tmp/emri/${id}` })];
    const fetchMock = installRunFetch(runs, id);
    selectHash(id);

    render(<App />);

    expect(await screen.findByRole("heading", { name: id })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/run/stage%2001%2Freplica%20a");
    const requestedUrls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(requestedUrls).toContain("/api/runs/stage%2001%2Freplica%20a");
    expect(requestedUrls).toContain("/api/runs/stage%2001%2Freplica%20a/lineage");
  });

  it("shows a dedicated run-not-found state for a 404 detail response", async () => {
    const id = "missing/stage";
    installFetch((url) => {
      if (url === "/api/runs") return jsonResponse({ runs: [], warnings: [] });
      return jsonResponse({ detail: `run not found: ${id}` }, 404);
    });
    selectHash(id);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Run not found" })).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`${id} is not present in the backend run list`))).toBeInTheDocument();
  });
});

describe("add-run workflow", () => {
  async function exerciseAdd(status: number) {
    const initial = makeSummary({ id: "stage_00" });
    const added = makeSummary({ id: "new run", path: "/scratch/emri/new run" });
    let listCalls = 0;
    const fetchMock = installFetch((url, init) => {
      if (url === "/api/runs" && !init?.method) {
        listCalls += 1;
        return jsonResponse({ runs: listCalls === 1 ? [initial] : [initial, added], warnings: [] });
      }
      if (url === "/api/runs" && init?.method === "POST") return jsonResponse(added, status);
      if (url.includes("/lineage")) return jsonResponse({ chain: makeLineage([added.id]) });
      if (url.includes("/api/runs/")) return jsonResponse(makeDetail(added.id));
      throw new Error(`unexpected request: ${url}`);
    });
    render(<App />);
    await screen.findByRole("button", { name: /stage_00/ });

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Server run folder path"), "/scratch/emri/new run");
    await user.click(screen.getByRole("button", { name: "add" }));

    expect(await screen.findByText(/Run new run was added and the list was refreshed/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, request]) =>
      request?.method === "POST" && request.body === JSON.stringify({ path: "/scratch/emri/new run" }),
    )).toBe(true);
  }

  it("handles a 201 Created add-run response", async () => {
    await exerciseAdd(201);
  });

  it("handles a 200 already-registered add-run response", async () => {
    await exerciseAdd(200);
  });

  it("validates an empty path in the browser and does not post", async () => {
    const fetchMock = installRunFetch([makeSummary()]);
    render(<App />);
    await screen.findByRole("button", { name: /stage_00/ });

    await userEvent.setup().click(screen.getByRole("button", { name: "add" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Enter a server-side run directory path.");
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  });

  it("surfaces a JSON 422 detail from the add-run endpoint", async () => {
    const fetchMock = installFetch((url, init) => {
      if (url === "/api/runs" && !init?.method) return jsonResponse({ runs: [], warnings: [] });
      if (url === "/api/runs" && init?.method === "POST") return jsonResponse({ detail: "run folder has no marker" }, 422);
      throw new Error(`unexpected request: ${url}`);
    });
    render(<App />);
    await screen.findByRole("heading", { name: "No runs discovered" });

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Server run folder path"), "/not/a/run");
    await user.click(screen.getByRole("button", { name: "add" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("run folder has no marker");
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });
});

describe("detail, diagnostics, plots, and theme controls", () => {
  function renderDetail() {
    const run = makeSummary({ id: "stage_02", from_run: "stage_01" });
    const fetchMock = installRunFetch([run], run.id);
    selectHash(run.id);
    render(<App />);
    return { run, fetchMock };
  }

  it("renders manifest groups, best coordinates, diagnostics, samples, and unset values", async () => {
    renderDetail();

    expect(await screen.findByRole("heading", { name: "stage_02" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "manifest" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "best point" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "n_sigma_to_contain" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "best_per_process" })).toBeInTheDocument();
    expect(screen.getAllByText("search coordinates", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getByText("total samples")).toBeInTheDocument();
    expect(screen.getAllByText("unset").length).toBeGreaterThan(0);
  });

  it("navigates from the lineage strip to another real run", async () => {
    const runs = [
      makeSummary({ id: "stage_00", from_run: null }),
      makeSummary({ id: "stage_01", from_run: "stage_00", kind: "from_run" }),
      makeSummary({ id: "stage_02", from_run: "stage_01", kind: "from_run" }),
    ];
    installFetch((url) => {
      if (url === "/api/runs") return jsonResponse({ runs, warnings: [] });
      if (url.includes("/lineage")) return jsonResponse({ chain: makeLineage(["stage_00", "stage_01", "stage_02"]) });
      if (url.includes("stage_01")) return jsonResponse(makeDetail("stage_01"));
      return jsonResponse(makeDetail("stage_02"));
    });
    selectHash("stage_02");
    render(<App />);

    expect(await screen.findByRole("heading", { name: "stage_02" })).toBeInTheDocument();
    const lineage = screen.getByLabelText("Run lineage");
    await userEvent.setup().click(within(lineage).getByRole("button", { name: /stage_01/ }));

    expect(window.location.hash).toBe("#/run/stage_01");
    expect(await screen.findByRole("heading", { name: "stage_01" })).toBeInTheDocument();
  });

  it("updates corner query parameters and keeps the PNG download tied to the request", async () => {
    renderDetail();
    await screen.findByAltText("Corner plot for run stage_02");

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("top_n"), "100");
    await user.type(screen.getByLabelText("title"), "custom title");
    await user.click(screen.getByLabelText("annotate"));
    await user.click(screen.getByLabelText("truth"));
    await user.click(screen.getAllByRole("button", { name: "paper" })[0]);

    await waitFor(() => {
      const image = screen.getByAltText("Corner plot for run stage_02");
      const src = image.getAttribute("src") ?? "";
      expect(src).toContain("top_n=100");
      expect(src).toContain("title=custom+title");
      expect(src).toContain("annotate=false");
      expect(src).toContain("truth=false");
      expect(src).toContain("theme=paper");
    });
    const image = screen.getByAltText("Corner plot for run stage_02");
    const download = screen.getAllByRole("link", { name: "download PNG" })[0];
    expect(download.getAttribute("href")).toBe(image.getAttribute("src"));
    expect(download).toHaveAttribute("download", "corner.png");
  });

  it("updates connection n, range, ylabel, progress, and theme query parameters", async () => {
    renderDetail();
    const image = await screen.findByAltText("Connection plot for run stage_02");

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("n"), "161");
    await user.selectOptions(screen.getByLabelText("t_range"), "0.0,1.0");
    await user.type(screen.getByLabelText("ylabel"), "statistic score");
    await user.click(screen.getByLabelText("progress"));
    await user.click(screen.getAllByRole("button", { name: "paper" })[1]);

    await waitFor(() => {
      const image = screen.getByAltText("Connection plot for run stage_02");
      const src = image.getAttribute("src") ?? "";
      expect(src).toContain("n=161");
      expect(src).toContain("t_range=0.0%2C1.0");
      expect(src).toContain("ylabel=statistic+score");
      expect(src).toContain("progress=true");
      expect(src).toContain("theme=paper");
    });
  });

  it("persists the dark/light shell theme and exposes an accessible toggle", async () => {
    installRunFetch([makeSummary()]);
    render(<App />);
    await screen.findByRole("button", { name: /stage_00/ });

    const toggle = screen.getByRole("button", { name: "Switch to light theme" });
    await userEvent.setup().click(toggle);

    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem("emrisearch-theme")).toBe("light");
  });

  it("keeps plot images and controls labeled for keyboard and assistive technology", async () => {
    renderDetail();

    expect(await screen.findByAltText("Corner plot for run stage_02")).toBeInTheDocument();
    expect(screen.getByAltText("Connection plot for run stage_02")).toBeInTheDocument();
    expect(screen.getByLabelText("Server run folder path")).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "rescan" })).toBeEnabled();
    expect(screen.getAllByRole("link", { name: "download PNG" })).toHaveLength(2);
  });
});
