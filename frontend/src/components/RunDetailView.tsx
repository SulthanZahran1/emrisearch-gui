import { BestDiagnostics } from "./BestDiagnostics";
import { ManifestSections } from "./ManifestSections";
import { PlotsPanel } from "./PlotsPanel";
import type { LineageItem, RunDetail } from "../types";
import { displayValue, lineageLabel } from "../format";
import { isRecord } from "../format";

interface RunDetailViewProps {
  detail: RunDetail;
  lineage: LineageItem[];
  lineageError: string | null;
  appTheme: "dark" | "light";
  onSelectRun: (runId: string) => void;
}

function Fact({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="fact">
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
    </div>
  );
}

export function RunDetailView({
  detail,
  lineage,
  lineageError,
  appTheme,
  onSelectRun,
}: RunDetailViewProps) {
  const groups = isRecord(detail.manifest_groups) ? detail.manifest_groups : {};
  const obs = isRecord(groups.obs) ? groups.obs : {};
  const space = isRecord(groups.space) ? groups.space : {};
  const dimensions = Array.isArray(space.dimensions) ? space.dimensions : [];
  const statistic = isRecord(groups.statistic) ? groups.statistic : {};
  const seeding = isRecord(groups.seeding) ? groups.seeding : {};
  const seedingKind = seeding.kind ?? detail.summary.kind;
  const runPath = detail.path ?? detail.summary.path;
  const chain = lineage.length > 0 ? lineage : [{
    id: detail.summary.id,
    path: detail.summary.path,
    kind: detail.summary.kind,
  }];

  return (
    <>
      <header className="run-header">
        <div className="lineage" aria-label="Run lineage">
          {chain.map((item, index) => (
            <span className="lineage-item-wrap" key={`${item.id}-${index}`}>
              <button
                type="button"
                className={`lineage-node${item.id === detail.summary.id ? " current" : ""}`}
                onClick={() => onSelectRun(item.id)}
                aria-current={item.id === detail.summary.id ? "page" : undefined}
                title={item.path}
              >
                <span className="lineage-index">{String(index + 1).padStart(2, "0")}</span>
                <span>{item.id}</span>
                <small>{lineageLabel(item.kind)}</small>
              </button>
              {index < chain.length - 1 && <span className="lineage-arrow" aria-hidden="true">→</span>}
            </span>
          ))}
        </div>
        {lineageError && <p className="inline-warning" role="status">Lineage could not be loaded: {lineageError}</p>}
        <h1 className="run-title">{detail.summary.id}</h1>
        <p className="run-path" title={displayValue(runPath)}>{displayValue(runPath)}</p>
        <div className="fact-strip">
          <Fact label="statistic" value={statistic.kind ?? detail.summary.statistic} />
          <Fact label="T" value={obs.T} />
          <Fact label="dimensions" value={dimensions.length || detail.summary.ndim} />
          <Fact label="samples" value={detail.samples?.n_samples} />
          <Fact label="seeding" value={seedingKind} />
          <Fact label="result" value={detail.summary.result_kind} />
        </div>
      </header>

      {detail.warnings?.length > 0 && (
        <div className="detail-warnings" role="status" aria-live="polite">
          {detail.warnings.map((warning, index) => <p key={`${warning}-${index}`}>{warning}</p>)}
        </div>
      )}

      <ManifestSections detail={detail} />
      <BestDiagnostics detail={detail} />
      <PlotsPanel key={detail.summary.id} runId={detail.summary.id} appTheme={appTheme} />
    </>
  );
}
