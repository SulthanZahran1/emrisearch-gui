import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { RunSummary } from "../types";
import {
  displayValue,
  formatLogDensity,
  groupRunsByChain,
  lineageLabel,
} from "../format";

interface RunRailProps {
  runs: RunSummary[];
  warnings: string[];
  activeId: string | null;
  loading: boolean;
  refreshing: boolean;
  listError: string | null;
  onRefresh: () => void;
  onSelect: (runId: string) => void;
  onAddRun: (path: string) => Promise<RunSummary>;
}

export function RunRail({
  runs,
  warnings,
  activeId,
  loading,
  refreshing,
  listError,
  onRefresh,
  onSelect,
  onAddRun,
}: RunRailProps) {
  const [path, setPath] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [addMessage, setAddMessage] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const groups = useMemo(() => groupRunsByChain(runs), [runs]);
  const discoveredPath = runs[0]?.path;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = path.trim();
    if (!trimmed) {
      setAddError("Enter a server-side run directory path.");
      setAddMessage(null);
      return;
    }
    setAddError(null);
    setAddMessage(null);
    setAdding(true);
    try {
      const registered = await onAddRun(trimmed);
      setPath("");
      setAddMessage(`Run ${registered.id} was added and the list was refreshed.`);
    } catch (error) {
      setAddError(error instanceof Error ? error.message : "Could not add this run.");
    } finally {
      setAdding(false);
    }
  }

  return (
    <aside className="rail" aria-label="Run explorer">
      <div className="rail-header">
        <div className="wordmark">
          emri<span>search</span> explorer
        </div>
        <div className="root-label" title={discoveredPath ?? undefined}>
          <span>local roots</span>
          {discoveredPath ? <code>discovered: {discoveredPath}</code> : <code>waiting for backend roots</code>}
        </div>
      </div>

      <div className="rail-actions">
        <button
          type="button"
          className="button button-ghost"
          onClick={onRefresh}
          disabled={loading || refreshing}
          aria-busy={loading || refreshing}
        >
          {refreshing ? "scanning" : "rescan"}
        </button>
        <button
          type="button"
          className="button button-ghost"
          onClick={() => document.getElementById("add-run-path")?.focus()}
        >
          add run
        </button>
      </div>

      <form className="add-run-form" onSubmit={submit}>
        <label htmlFor="add-run-path">Server run folder path</label>
        <div className="add-run-controls">
          <input
            id="add-run-path"
            name="path"
            type="text"
            value={path}
            onChange={(event) => setPath(event.target.value)}
            placeholder="/scratch/emri/stage_02"
            spellCheck={false}
            autoComplete="off"
            disabled={adding}
          />
          <button type="submit" className="button button-primary" disabled={adding}>
            {adding ? "adding" : "add"}
          </button>
        </div>
        <p className="field-help">Use a path visible to the FastAPI server. Browser folder selection cannot expose that path.</p>
        {addError && <p className="form-error" role="alert">{addError}</p>}
        {addMessage && <p className="form-success" role="status">{addMessage}</p>}
      </form>

      {listError && <p className="rail-error" role="alert">{listError}</p>}
      {warnings.length > 0 && (
        <div className="rail-warnings" role="status" aria-live="polite">
          <span className="rail-warning-title">scan warnings</span>
          <ul>
            {warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}
          </ul>
        </div>
      )}

      <nav className="run-list" aria-label="Discovered runs">
        {loading && runs.length === 0 ? (
          <div className="rail-skeletons" aria-label="Loading discovered runs">
            {Array.from({ length: 5 }, (_, index) => <div className="skeleton rail-skeleton" key={index} />)}
          </div>
        ) : groups.length === 0 ? (
          <p className="rail-empty">No discovered runs.</p>
        ) : (
          groups.map((group) => (
            <div className="chain-group" key={group.key}>
              <div className="chain-label">chain: {group.label}</div>
              {group.runs.map((run) => (
                <button
                  type="button"
                  className={`run-row${run.id === activeId ? " active" : ""}`}
                  key={run.id}
                  onClick={() => onSelect(run.id)}
                  aria-current={run.id === activeId ? "page" : undefined}
                  title={run.path}
                >
                  <span className="run-name">{run.id}</span>
                  <span className="run-best">{formatLogDensity(run.best_log_density)}</span>
                  <span className="run-kind">{lineageLabel(run.kind)}</span>
                  <span className="run-meta">
                    {run.ndim === null || run.ndim === undefined ? "unset" : `${displayValue(run.ndim)}d`}
                    <span className="run-statistic">{displayValue(run.statistic)}</span>
                  </span>
                </button>
              ))}
            </div>
          ))
        )}
      </nav>
    </aside>
  );
}
