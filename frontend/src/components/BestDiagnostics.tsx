import type { BestDimension, BestPoint, BestPerProcessTable, Diagnostics, NSigmaRow, ProcessBest, RunDetail } from "../types";
import {
  bestProcessStatus,
  displayValue,
  formatInteger,
  formatLogDensity,
  formatPercent,
} from "../format";

function EmptyRow({ colSpan, label }: { colSpan: number; label: string }) {
  return <tr><td colSpan={colSpan} className="table-empty">{label}</td></tr>;
}

function BestPointPanel({ best }: { best: BestPoint }) {
  const dimensions: BestDimension[] = Array.isArray(best.dimensions) ? best.dimensions : [];
  return (
    <div className="best-panel">
      <div className="metric-label">best log-density</div>
      <div className="big-metric">{formatLogDensity(best.log_density)}</div>
      <div className="metric-note">highest finite value reported by the run</div>
      <div className="table-scroll table-spaced">
        <table className="data-table">
          <caption className="sr-only">Best point search and physical coordinates</caption>
          <thead>
            <tr>
              <th scope="col">parameter</th>
              <th scope="col">transform</th>
              <th scope="col" className="numeric">search</th>
              <th scope="col" className="numeric">physical</th>
              <th scope="col" className="numeric">n_sigma</th>
            </tr>
          </thead>
          <tbody>
            {dimensions.length === 0 ? (
              <EmptyRow colSpan={5} label="Best coordinates are unavailable." />
            ) : dimensions.map((dimension, index) => {
              const highlighted = typeof dimension.n_sigma === "number" && dimension.n_sigma > 2;
              return (
                <tr key={`${dimension.name}-${index}`}>
                  <td>{displayValue(dimension.name)}</td>
                  <td>{displayValue(dimension.transform)}</td>
                  <td className="numeric">{displayValue(dimension.search)}</td>
                  <td className="numeric">{displayValue(dimension.physical)}</td>
                  <td className={`numeric ${highlighted ? "value-alert" : ""}`}>{displayValue(dimension.n_sigma)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="table-note">Search coordinates are sampler values. Physical coordinates use the recorded transform.</p>
    </div>
  );
}

function NSigmaTable({ table }: { table: Diagnostics["n_sigma_to_contain"] }) {
  const rows: NSigmaRow[] = Array.isArray(table?.rows) ? table.rows : [];
  return (
    <div className="diagnostic-block">
      <div className="subheading-row">
        <h3>n_sigma_to_contain</h3>
        <span className={`status-badge ${table?.available ? "status-ok" : "status-muted"}`}>
          {table?.available ? "available" : "unset"}
        </span>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <caption className="sr-only">Distance between best point and truth</caption>
          <thead>
            <tr>
              <th scope="col">parameter</th>
              <th scope="col" className="numeric">best</th>
              <th scope="col" className="numeric">truth</th>
              <th scope="col" className="numeric">sigma</th>
              <th scope="col" className="numeric">n_sigma</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? <EmptyRow colSpan={5} label="No containment rows reported." /> : rows.map((row, index) => {
              const highlighted = typeof row.n_sigma === "number" && row.n_sigma > 2;
              return (
                <tr key={`${row.name}-${index}`}>
                  <td>{displayValue(row.name)}</td>
                  <td className="numeric">{displayValue(row.best)}</td>
                  <td className="numeric">{displayValue(row.truth)}</td>
                  <td className="numeric">{displayValue(row.sigma)}</td>
                  <td className={`numeric ${highlighted ? "value-alert" : ""}`}>{displayValue(row.n_sigma)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ProcessTable({ table }: { table: BestPerProcessTable | undefined }) {
  const rows: ProcessBest[] = Array.isArray(table?.rows) ? table.rows : [];
  const status = bestProcessStatus(table?.merged);
  const statusClass = status === "merged" ? "status-ok" : status === "unmerged" ? "status-alert" : "status-muted";
  return (
    <div className="diagnostic-block">
      <div className="subheading-row">
        <h3>best_per_process</h3>
        <span className={`status-badge ${statusClass}`}>{status}</span>
      </div>
      <p className="diagnostic-summary">
        spread <strong>{displayValue(table?.spread)}</strong>
        {table?.available === false ? "; process state is unavailable" : ""}
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <caption className="sr-only">Best point recorded by each process</caption>
          <thead>
            <tr>
              <th scope="col">process</th>
              <th scope="col" className="numeric">best log-density</th>
              <th scope="col">search coordinates</th>
              <th scope="col">physical coordinates</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? <EmptyRow colSpan={4} label="No process rows reported." /> : rows.map((row, index) => (
              <tr key={`${row.process}-${index}`}>
                <td>{displayValue(row.process)}</td>
                <td className="numeric">{formatLogDensity(row.log_density)}</td>
                <td>{displayValue(row.search_coordinates)}</td>
                <td>{displayValue(row.physical_coordinates)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SampleSummary({ detail }: { detail: RunDetail }) {
  const total = detail.samples?.n_samples;
  const finite = detail.samples?.n_finite;
  return (
    <div className="sample-summary">
      <div className="sample-cell">
        <span>total samples</span>
        <strong>{formatInteger(total)}</strong>
      </div>
      <div className="sample-cell">
        <span>finite samples</span>
        <strong>{formatInteger(finite)}</strong>
      </div>
      <div className="sample-cell">
        <span>finite share</span>
        <strong>{formatPercent(finite, total)}</strong>
      </div>
    </div>
  );
}

export function BestDiagnostics({ detail }: { detail: RunDetail }) {
  const best = detail.best ?? {};
  const diagnostics = detail.diagnostics ?? {};
  return (
    <section className="section-block" id="best">
      <div className="section-heading">
        <div>
          <h2>best point</h2>
          <p>Search coordinates, physical values, and convergence diagnostics.</p>
        </div>
        <span className="section-note">{displayValue(detail.summary?.statistic)}</span>
      </div>
      <div className="best-layout">
        <BestPointPanel best={best} />
        <div className="diagnostics-column">
          <NSigmaTable table={diagnostics.n_sigma_to_contain} />
          <ProcessTable table={diagnostics.best_per_process} />
          <SampleSummary detail={detail} />
        </div>
      </div>
    </section>
  );
}
