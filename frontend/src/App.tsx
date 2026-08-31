import { useCallback, useEffect, useRef, useState } from "react";
import { addRun, ApiError, getLineage, getRunDetail, listRuns } from "./api";
import { AppShell } from "./components/AppShell";
import { ConfigBuilder } from "./components/ConfigBuilder";
import { RunDetailView } from "./components/RunDetailView";
import { RunRail } from "./components/RunRail";
import { LoadingState, StatePanel } from "./components/States";
import type { LineageItem, RunDetail, RunSummary } from "./types";

export type Theme = "dark" | "light";

function routeIdFromHash(): string | null {
  const hash = window.location.hash;
  if (!hash.startsWith("#/run/")) return null;
  const encoded = hash.slice("#/run/".length);
  if (!encoded) return null;
  try {
    return decodeURIComponent(encoded);
  } catch {
    return encoded;
  }
}

function useRunRoute(): [string | null, (runId: string | null) => void] {
  const [runId, setRunId] = useState<string | null>(() => routeIdFromHash());

  useEffect(() => {
    const handleHashChange = () => setRunId(routeIdFromHash());
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const navigate = useCallback((nextId: string | null) => {
    const nextHash = nextId ? `#/run/${encodeURIComponent(nextId)}` : "#/";
    if (window.location.hash === nextHash) {
      setRunId(nextId);
      return;
    }
    window.location.hash = nextHash;
  }, []);

  return [runId, navigate];
}

function initialTheme(): Theme {
  try {
    const stored = window.localStorage.getItem("emrisearch-theme");
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    // Storage can be disabled by the browser. The system preference is enough.
  }
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(() => initialTheme());
  const [view, setView] = useState<"explorer" | "config-builder">("explorer");
  const [selectedId, navigate] = useRunRoute();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [listWarnings, setListWarnings] = useState<string[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<ApiError | null>(null);
  const [detailReload, setDetailReload] = useState(0);
  const [lineage, setLineage] = useState<LineageItem[]>([]);
  const [lineageError, setLineageError] = useState<string | null>(null);
  const listRequestRef = useRef<AbortController | null>(null);
  const detailRequestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem("emrisearch-theme", theme);
    } catch {
      // Persisting the theme is best effort.
    }
  }, [theme]);

  useEffect(() => {
    document.title = selectedId ? `${selectedId} | emrisearch explorer` : "emrisearch explorer";
  }, [selectedId]);

  const refreshRuns = useCallback(async (initial = false): Promise<RunSummary[]> => {
    listRequestRef.current?.abort();
    const controller = new AbortController();
    listRequestRef.current = controller;
    if (initial) setListLoading(true);
    else {
      setRefreshing(true);
      setListLoading(true);
    }
    setListError(null);
    try {
      const response = await listRuns(controller.signal);
      setRuns(Array.isArray(response.runs) ? response.runs : []);
      setListWarnings(Array.isArray(response.warnings) ? response.warnings : []);
      return Array.isArray(response.runs) ? response.runs : [];
    } catch (error) {
      if (controller.signal.aborted) return [];
      const apiError = error instanceof ApiError ? error : new ApiError(0, "Could not load runs.");
      setListError(apiError.detail);
      setListWarnings([]);
      return [];
    } finally {
      if (!controller.signal.aborted) {
        setListLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void refreshRuns(true);
    return () => listRequestRef.current?.abort();
  }, [refreshRuns]);

  useEffect(() => {
    detailRequestRef.current?.abort();
    if (!selectedId) {
      setDetail(null);
      setDetailError(null);
      setLineage([]);
      setLineageError(null);
      setDetailLoading(false);
      return;
    }

    const controller = new AbortController();
    detailRequestRef.current = controller;
    setDetailLoading(true);
    setDetail(null);
    setDetailError(null);
    setLineage([]);
    setLineageError(null);

    getRunDetail(selectedId, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted) setDetail(response);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setDetailError(error instanceof ApiError ? error : new ApiError(0, "Could not load run details."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });

    getLineage(selectedId, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted) setLineage(Array.isArray(response.chain) ? response.chain : []);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof ApiError ? error.detail : "Could not load lineage.";
        setLineageError(message);
      });

    return () => controller.abort();
  }, [selectedId, detailReload]);

  const handleAddRun = useCallback(async (path: string): Promise<RunSummary> => {
    const registered = await addRun(path);
    const freshRuns = await refreshRuns();
    const refreshed = freshRuns.find((run) => run.id === registered.id) ?? registered;
    navigate(refreshed.id);
    return refreshed;
  }, [navigate, refreshRuns]);

  const retryDetail = useCallback(() => {
    setDetailReload((current) => current + 1);
  }, []);

  const selectedInList = selectedId ? runs.some((run) => run.id === selectedId) : false;
  const runNotFound = Boolean(selectedId && detailError?.status === 404);
  const showListError = Boolean(listError && runs.length === 0 && !selectedId);
  const hasLoadedRuns = !listLoading;

  let content: React.ReactNode;
  if (view === "config-builder") {
    content = <ConfigBuilder />;
  } else if (showListError) {
    content = <StatePanel title="API unavailable" message={listError ?? "The run list could not be loaded."} actionLabel="retry" onAction={() => void refreshRuns()} tone="error" />;
  } else if (!selectedId) {
    if (listLoading) {
      content = <LoadingState />;
    } else if (runs.length === 0) {
      content = <StatePanel title="No runs discovered" message="The backend found no manifest.json or sampler_state.pkl under its configured roots. Add a server-side run folder to begin." />;
    } else {
      content = <StatePanel title="Select a run to inspect" message="Choose a discovered run from the rail. The explorer reads details and plots from the FastAPI endpoints." />;
    }
  } else if (runNotFound) {
    content = (
      <StatePanel
        title="Run not found"
        message={`${selectedId} is not present in the backend run list. It may have moved or the route may be wrong.`}
        actionLabel="back to run list"
        onAction={() => navigate(null)}
      />
    );
  } else if (detailError) {
    content = (
      <StatePanel
        title="Could not load run"
        message={detailError.detail}
        actionLabel="retry"
        onAction={retryDetail}
        tone="error"
      />
    );
  } else if (detailLoading || !detail) {
    content = <LoadingState detail />;
  } else {
    content = (
      <RunDetailView
        detail={detail}
        lineage={lineage}
        lineageError={lineageError}
        appTheme={theme}
        onSelectRun={navigate}
      />
    );
  }

  return (
    <AppShell
      theme={theme}
      hasRun={Boolean(detail && selectedId)}
      view={view}
      onToggleTheme={() => setTheme((current) => current === "dark" ? "light" : "dark")}
      onToggleView={() => setView((current: "explorer" | "config-builder") => current === "explorer" ? "config-builder" : "explorer")}
      rail={(
        <RunRail
          runs={runs}
          warnings={listWarnings}
          activeId={selectedId}
          loading={listLoading}
          refreshing={refreshing}
          listError={listError}
          onRefresh={() => void refreshRuns()}
          onSelect={navigate}
          onAddRun={handleAddRun}
        />
      )}
    >
      {selectedId && hasLoadedRuns && !selectedInList && !detail && !detailError && (
        <p className="inline-warning" role="status">Loading a direct route for {selectedId}.</p>
      )}
      {content}
    </AppShell>
  );
}
