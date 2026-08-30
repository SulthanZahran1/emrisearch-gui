import type { ReactNode } from "react";
import type { ManifestGroups, RunDetail, SearchDimension, SearchSpace } from "../types";
import { displayValue, isRecord } from "../format";

interface ValueGridProps {
  values: unknown;
  emptyLabel?: string;
}

function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function ValueGrid({ values, emptyLabel = "No values reported." }: ValueGridProps) {
  const entries = Object.entries(asRecord(values));
  if (entries.length === 0) return <p className="muted-empty">{emptyLabel}</p>;
  return (
    <div className="kv-grid">
      {entries.map(([key, value]) => (
        <div className="kv" key={key}>
          <div className="kv-key">{key}</div>
          <div className="kv-value" title={displayValue(value)}>{displayValue(value)}</div>
        </div>
      ))}
    </div>
  );
}

function GroupBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="manifest-group">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

function SearchSpaceTable({ space }: { space: SearchSpace | undefined }) {
  const dimensions: SearchDimension[] = Array.isArray(space?.dimensions) ? space.dimensions : [];
  return (
    <div className="table-scroll">
      <table className="data-table">
        <caption className="sr-only">Free search-space dimensions</caption>
        <thead>
          <tr>
            <th scope="col">parameter</th>
            <th scope="col">search coordinate</th>
            <th scope="col">transform</th>
            <th scope="col" className="numeric">lo</th>
            <th scope="col" className="numeric">hi</th>
          </tr>
        </thead>
        <tbody>
          {dimensions.length === 0 ? (
            <tr><td colSpan={5} className="table-empty">No free dimensions reported.</td></tr>
          ) : dimensions.map((dimension, index) => (
            <tr key={`${dimension.name}-${index}`}>
              <td>{displayValue(dimension.name)}</td>
              <td>{displayValue(dimension.search_coord)}</td>
              <td>{displayValue(dimension.transform)}</td>
              <td className="numeric">{displayValue(dimension.lo)}</td>
              <td className="numeric">{displayValue(dimension.hi)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? "unset";
  } catch {
    return displayValue(value);
  }
}

export function ManifestSections({ detail }: { detail: RunDetail }) {
  const groups: ManifestGroups = isRecord(detail.manifest_groups) ? detail.manifest_groups : {};
  const space = isRecord(groups.space) ? groups.space as SearchSpace : undefined;
  const version = groups.emrisearch_version;
  const out = groups.out ?? detail.path;

  return (
    <section className="section-block" id="manifest">
      <div className="section-heading">
        <div>
          <h2>manifest</h2>
          <p>Configuration recorded beside the sampler state.</p>
        </div>
        <span className="section-note">emrisearch {displayValue(version)}</span>
      </div>

      <GroupBlock title="source">
        <ValueGrid values={groups.source} />
      </GroupBlock>

      <GroupBlock title="observation / noise / modes">
        <div className="three-group-grid">
          <div>
            <h4>observation</h4>
            <ValueGrid values={groups.obs} />
          </div>
          <div>
            <h4>noise</h4>
            <ValueGrid values={groups.noise} />
          </div>
          <div>
            <h4>modes</h4>
            <ValueGrid values={groups.modes} />
          </div>
        </div>
      </GroupBlock>

      <GroupBlock title="statistic">
        <ValueGrid values={groups.statistic} />
      </GroupBlock>

      <GroupBlock title="search space">
        <SearchSpaceTable space={space} />
      </GroupBlock>

      <GroupBlock title="fixed">
        <ValueGrid values={space?.fixed} />
      </GroupBlock>

      <GroupBlock title="sampler">
        <ValueGrid values={groups.sampler} />
      </GroupBlock>

      <GroupBlock title="seeding">
        <ValueGrid values={groups.seeding} />
      </GroupBlock>

      <div className="manifest-footer-facts">
        <div>
          <span>out</span>
          <code title={displayValue(out)}>{displayValue(out)}</code>
        </div>
        <div>
          <span>emrisearch_version</span>
          <code>{displayValue(version)}</code>
        </div>
      </div>

      {Object.keys(detail.manifest ?? {}).length > 0 && (
        <details className="raw-details">
          <summary>view raw manifest</summary>
          <pre>{safeJson(detail.manifest)}</pre>
        </details>
      )}
    </section>
  );
}
