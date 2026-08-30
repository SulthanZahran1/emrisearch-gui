import { useEffect, useState } from "react";
import { apiUrl, encodedRunPath } from "../api";

export type PlotTheme = "default" | "dark" | "paper";

const cornerTopValues = [10, 20, 50, 100] as const;
const connectionNValues = [41, 81, 161] as const;
const connectionRanges = [
  { value: "-0.3,1.3", label: "-0.3, 1.3" },
  { value: "-0.5,1.5", label: "-0.5, 1.5" },
  { value: "0.0,1.0", label: "0.0, 1.0" },
] as const;

interface CornerOptions {
  top_n: number;
  title: string;
  annotate: boolean;
  truth: boolean;
  theme: PlotTheme;
}

interface ConnectionOptions {
  n: number;
  t_range: string;
  ylabel: string;
  progress: boolean;
  theme: PlotTheme;
}

function cornerUrl(runId: string, options: CornerOptions): string {
  const query = new URLSearchParams();
  query.set("top_n", String(options.top_n));
  if (options.title.trim()) query.set("title", options.title.trim());
  query.set("annotate", String(options.annotate));
  query.set("truth", String(options.truth));
  query.set("theme", options.theme);
  return apiUrl(`${encodedRunPath(runId, "/plots/corner")}?${query.toString()}`);
}

function connectionUrl(runId: string, options: ConnectionOptions): string {
  const query = new URLSearchParams();
  query.set("n", String(options.n));
  query.set("t_range", options.t_range);
  if (options.ylabel.trim()) query.set("ylabel", options.ylabel.trim());
  query.set("progress", String(options.progress));
  query.set("theme", options.theme);
  return apiUrl(`${encodedRunPath(runId, "/plots/connection")}?${query.toString()}`);
}

function ThemeControl({ value, onChange }: { value: PlotTheme; onChange: (value: PlotTheme) => void }) {
  return (
    <fieldset className="control-fieldset">
      <legend>theme</legend>
      <div className="segmented-control">
        {(["default", "dark", "paper"] as PlotTheme[]).map((theme) => (
          <button
            type="button"
            className={value === theme ? "segment active" : "segment"}
            key={theme}
            aria-pressed={value === theme}
            onClick={() => onChange(theme)}
          >
            {theme}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

interface PlotCardProps {
  title: string;
  caption: string;
  src: string;
  alt: string;
  children: React.ReactNode;
}

function PlotCard({ title, caption, src, alt, children }: PlotCardProps) {
  const [imageError, setImageError] = useState(false);
  useEffect(() => setImageError(false), [src]);

  return (
    <figure className="plot-card">
      <div className="plot-header">
        <span className="plot-title">{title}</span>
        <a className="button button-ghost plot-download" href={src} download={`${title}.png`}>
          download PNG
        </a>
      </div>
      <div className="plot-controls">{children}</div>
      <div className="plot-image">
        {imageError ? (
          <div className="plot-fallback" role="alert">The server plot request could not be displayed.</div>
        ) : (
          <img key={src} src={src} alt={alt} onError={() => setImageError(true)} />
        )}
      </div>
      <figcaption className="plot-caption">{caption}</figcaption>
      <details className="request-details">
        <summary>view current request</summary>
        <code>GET {src}</code>
      </details>
    </figure>
  );
}

export function PlotsPanel({ runId, appTheme }: { runId: string; appTheme: "dark" | "light" }) {
  const [corner, setCorner] = useState<CornerOptions>({
    top_n: 10,
    title: "",
    annotate: true,
    truth: true,
    theme: appTheme === "dark" ? "dark" : "default",
  });
  const [connection, setConnection] = useState<ConnectionOptions>({
    n: 81,
    t_range: "-0.3,1.3",
    ylabel: "",
    progress: false,
    theme: appTheme === "dark" ? "dark" : "default",
  });

  const cornerSrc = cornerUrl(runId, corner);
  const connectionSrc = connectionUrl(runId, connection);

  return (
    <section className="section-block" id="plots">
      <div className="section-heading">
        <div>
          <h2>plots</h2>
          <p>Server-rendered PNGs. Change a control to request a new image.</p>
        </div>
        <span className="section-note">matplotlib endpoints</span>
      </div>
      <div className="plot-grid">
        <PlotCard
          title="corner"
          caption="Top search points with optional truth reference and annotations."
          src={cornerSrc}
          alt={`Corner plot for run ${runId}`}
        >
          <div className="plot-control-row">
            <ThemeControl value={corner.theme} onChange={(theme) => setCorner((current) => ({ ...current, theme }))} />
            <label className="control-field">
              <span>top_n</span>
              <select
                value={corner.top_n}
                onChange={(event) => setCorner((current) => ({ ...current, top_n: Number(event.target.value) }))}
              >
                {cornerTopValues.map((value) => <option value={value} key={value}>{value}</option>)}
              </select>
            </label>
            <label className="checkbox-control">
              <input
                type="checkbox"
                checked={corner.annotate}
                onChange={(event) => setCorner((current) => ({ ...current, annotate: event.target.checked }))}
              />
              annotate
            </label>
            <label className="checkbox-control">
              <input
                type="checkbox"
                checked={corner.truth}
                onChange={(event) => setCorner((current) => ({ ...current, truth: event.target.checked }))}
              />
              truth
            </label>
          </div>
          <label className="control-field control-field-wide">
            <span>title</span>
            <input
              type="text"
              value={corner.title}
              onChange={(event) => setCorner((current) => ({ ...current, title: event.target.value }))}
              placeholder="optional title override"
            />
          </label>
        </PlotCard>

        <PlotCard
          title="connection"
          caption="Statistic along the line from injection to recovered point."
          src={connectionSrc}
          alt={`Connection plot for run ${runId}`}
        >
          <div className="plot-control-row">
            <ThemeControl value={connection.theme} onChange={(theme) => setConnection((current) => ({ ...current, theme }))} />
            <label className="control-field">
              <span>n</span>
              <select
                value={connection.n}
                onChange={(event) => setConnection((current) => ({ ...current, n: Number(event.target.value) }))}
              >
                {connectionNValues.map((value) => <option value={value} key={value}>{value}</option>)}
              </select>
            </label>
            <label className="control-field">
              <span>t_range</span>
              <select
                value={connection.t_range}
                onChange={(event) => setConnection((current) => ({ ...current, t_range: event.target.value }))}
              >
                {connectionRanges.map((range) => <option value={range.value} key={range.value}>{range.label}</option>)}
              </select>
            </label>
            <label className="checkbox-control">
              <input
                type="checkbox"
                checked={connection.progress}
                onChange={(event) => setConnection((current) => ({ ...current, progress: event.target.checked }))}
              />
              progress
            </label>
          </div>
          <label className="control-field control-field-wide">
            <span>ylabel</span>
            <input
              type="text"
              value={connection.ylabel}
              onChange={(event) => setConnection((current) => ({ ...current, ylabel: event.target.value }))}
              placeholder="optional axis label"
            />
          </label>
          <p className="plot-help">The API may return a labeled placeholder when the heavy statistic stack is unavailable.</p>
        </PlotCard>
      </div>
    </section>
  );
}
