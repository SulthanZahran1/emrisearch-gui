import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  ApiError,
  getCanonicalConfig,
  previewConfig,
  saveConfig,
} from "../api";
import type { ArtifactBundleResponse, EMRIConfig } from "../types";
import { LoadingState, StatePanel } from "./States";

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function NumberField({
  label,
  value,
  step,
  onChange,
}: {
  label: string;
  value: number;
  step?: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="control-field control-field-number">
      <span>{label}</span>
      <input
        type="number"
        step={step ?? "any"}
        value={Number.isFinite(value) ? value : ""}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="control-field">
      <span>{label}</span>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function CheckField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="checkbox-control">
      <input
        type="checkbox"
        checked={value}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  );
}

function BoundEditor({
  name,
  lo,
  hi,
  onLo,
  onHi,
}: {
  name: string;
  lo: number;
  hi: number;
  onLo: (value: number) => void;
  onHi: (value: number) => void;
}) {
  return (
    <div className="bound-row">
      <span className="bound-name">{name}</span>
      <NumberField label="lo" value={lo} onChange={onLo} />
      <NumberField label="hi" value={hi} onChange={onHi} />
    </div>
  );
}

function ConfigEditor({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const obs = asRecord(config.obs);
  const space = asRecord(config.space);
  const free = Array.isArray(space.free) ? (space.free as Record<string, unknown>[]) : [];
  const statistic = asRecord(config.statistic);
  const options = asRecord(statistic.options);
  const sampler = asRecord(config.sampler);
  const seeding = asRecord(config.seeding);
  const pbs = asRecord(config.pbs);

  const patch = (path: string[], value: unknown) => {
    const next: Record<string, unknown> = JSON.parse(JSON.stringify(config));
    let cursor: Record<string, unknown> = next;
    for (const key of path.slice(0, -1)) {
      const child = cursor[key];
      cursor[key] = asRecord(child);
      cursor = cursor[key] as Record<string, unknown>;
    }
    cursor[path[path.length - 1]] = value;
    onChange(next);
  };

  const patchObs = (key: string, value: unknown) => patch(["obs", key], value);
  const patchSampler = (key: string, value: unknown) => patch(["sampler", key], value);
  const patchPbs = (key: string, value: unknown) => patch(["pbs", key], value);

  const setBound = (name: string, key: "lo" | "hi", value: number) => {
    const next: Record<string, unknown> = JSON.parse(JSON.stringify(config));
    const nextSpace = asRecord(next.space);
    const nextFree = Array.isArray(nextSpace.free)
      ? (nextSpace.free as Record<string, unknown>[]).map((row) => ({ ...row }))
      : [];
    for (const row of nextFree) {
      if (row.name === name) row[key] = value;
    }
    nextSpace.free = nextFree;
    next.space = nextSpace;
    onChange(next);
  };

  return (
    <div className="config-editor">
      <section className="config-section">
        <h3>source</h3>
        <div className="config-field-grid">
          <TextField
            label="catalogue preset"
            value={asString(config.source, "emri_c")}
            onChange={(value) => patch(["source"], value)}
          />
        </div>
      </section>

      <section className="config-section">
        <h3>observation</h3>
        <div className="config-field-grid">
          <NumberField label="T (years)" value={asNumber(obs.T)} onChange={(value) => patchObs("T", value)} />
          <NumberField label="dt (seconds)" value={asNumber(obs.dt)} onChange={(value) => patchObs("dt", value)} />
          <NumberField label="tdi_gen" value={asNumber(obs.tdi_gen)} step="1" onChange={(value) => patchObs("tdi_gen", value)} />
          <CheckField label="use_gpu" value={asBoolean(obs.use_gpu, true)} onChange={(value) => patchObs("use_gpu", value)} />
          <CheckField label="pad_output" value={asBoolean(obs.pad_output)} onChange={(value) => patchObs("pad_output", value)} />
        </div>
      </section>

      <section className="config-section">
        <h3>search space (intrinsic)</h3>
        <p className="config-help">Bounds are in search coordinates: log10 for m1/m2, identity otherwise.</p>
        {free.map((row) => (
          <BoundEditor
            key={asString(row.name)}
            name={asString(row.name)}
            lo={asNumber(row.lo)}
            hi={asNumber(row.hi)}
            onLo={(value) => setBound(asString(row.name), "lo", value)}
            onHi={(value) => setBound(asString(row.name), "hi", value)}
          />
        ))}
      </section>

      <section className="config-section">
        <h3>statistic</h3>
        <div className="config-field-grid">
          <TextField label="kind" value={asString(statistic.kind, "semicoherent")} onChange={(value) => patch(["statistic", "kind"], value)} />
          <NumberField
            label="N_seg"
            value={asNumber(options.N_seg, 12)}
            step="1"
            onChange={(value) => patch(["statistic", "options", "N_seg"], value)}
          />
        </div>
      </section>

      <section className="config-section">
        <h3>sampler</h3>
        <div className="config-field-grid">
          <NumberField label="n_seed" value={asNumber(sampler.n_seed)} step="1" onChange={(value) => patchSampler("n_seed", value)} />
          <NumberField label="num_iterations" value={asNumber(sampler.num_iterations)} step="1" onChange={(value) => patchSampler("num_iterations", value)} />
          <NumberField label="init_cov" value={asNumber(sampler.init_cov)} onChange={(value) => patchSampler("init_cov", value)} />
          <NumberField label="save_every" value={asNumber(sampler.save_every)} step="1" onChange={(value) => patchSampler("save_every", value)} />
          <NumberField label="sampler seed" value={asNumber(sampler.seed)} step="1" onChange={(value) => patchSampler("seed", value)} />
          <NumberField label="seeding n" value={asNumber(seeding.n)} step="1" onChange={(value) => patch(["seeding", "n"], value)} />
        </div>
      </section>

      <section className="config-section">
        <h3>output</h3>
        <div className="config-field-grid">
          <TextField label="run output directory" value={asString(config.out)} onChange={(value) => patch(["out"], value)} placeholder="/scratch/emri/emri_c_stage1_s12" />
        </div>
      </section>

      <section className="config-section">
        <h3>pbs</h3>
        <div className="config-field-grid">
          <TextField label="project" value={asString(pbs.project)} onChange={(value) => patchPbs("project", value)} />
          <TextField label="job name" value={asString(pbs.job_name)} onChange={(value) => patchPbs("job_name", value)} />
          <TextField label="walltime" value={asString(pbs.walltime)} onChange={(value) => patchPbs("walltime", value)} />
          <NumberField label="gpu_count" value={asNumber(pbs.gpu_count)} step="1" onChange={(value) => patchPbs("gpu_count", value)} />
          <TextField label="cuda module" value={asString(pbs.cuda_module)} onChange={(value) => patchPbs("cuda_module", value)} />
          <TextField label="venv activate" value={asString(pbs.venv_activate)} onChange={(value) => patchPbs("venv_activate", value)} />
        </div>
      </section>
    </div>
  );
}

function downloadArtifact(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ConfigBuilder() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ArtifactBundleResponse | null>(null);
  const [previewConfigValue, setPreviewConfigValue] = useState<EMRIConfig | null>(null);
  const [savedPaths, setSavedPaths] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [artifactDir, setArtifactDir] = useState("");
  const [overwrite, setOverwrite] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCanonicalConfig()
      .then((canonical) => {
        if (!cancelled) {
          setConfig(canonical);
          setLoadError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setLoadError(
            caught instanceof ApiError ? caught.detail : "Could not load the canonical preset.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handlePreview = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    if (!config) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    setSavedPaths([]);
    try {
      const response = await previewConfig(config);
      setPreview(response.artifacts);
      setPreviewConfigValue(response.config);
    } catch (caught) {
      setPreview(null);
      setPreviewConfigValue(null);
      setError(caught instanceof ApiError ? caught.detail : "Could not generate artifacts.");
    } finally {
      setBusy(false);
    }
  }, [config]);

  const handleSave = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    if (!config) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const response = await saveConfig(config, artifactDir, overwrite);
      setPreview(response.artifacts);
      setPreviewConfigValue(response.config);
      setSavedPaths(response.written_paths);
      setNotice(`Saved ${response.written_paths.length} artifact(s) to ${artifactDir}.`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : "Could not save artifacts.");
    } finally {
      setBusy(false);
    }
  }, [config, artifactDir, overwrite]);

  if (loadError) {
    return (
      <StatePanel tone="error" title="Config builder unavailable" message={loadError} />
    );
  }

  if (!config) {
    return <LoadingState />;
  }

  return (
    <section className="section-block" id="config-builder">
      <div className="section-heading">
        <div>
          <h2>config builder</h2>
          <p>Build and validate a canonical EMRI-C run, then generate inspectable Python/PBS artifacts. Nothing is executed or submitted.</p>
        </div>
        <span className="section-note">generate only</span>
      </div>

      <form className="config-builder-form" onSubmit={(event) => void handlePreview(event)}>
        <ConfigEditor config={config} onChange={setConfig} />

        <div className="config-actions">
          <button type="submit" className="button button-primary" disabled={busy}>
            {busy ? "generating..." : "generate artifacts"}
          </button>
        </div>
      </form>

      {error && (
        <div className="detail-warnings" role="alert">
          <p>{error}</p>
        </div>
      )}
      {notice && (
        <p className="inline-warning" role="status">{notice}</p>
      )}

      {preview && (
        <div className="artifact-preview">
          <div className="artifact-tabs">
            <details open>
              <summary>python artifact</summary>
              <pre className="artifact-code">{preview.python.content}</pre>
            </details>
            <details>
              <summary>pbs artifact</summary>
              <pre className="artifact-code">{preview.pbs.content}</pre>
            </details>
          </div>
          <div className="config-actions">
            <button
              type="button"
              className="button button-ghost"
              onClick={() => downloadArtifact(preview.python.filename, preview.python.content)}
            >
              download python
            </button>
            <button
              type="button"
              className="button button-ghost"
              onClick={() => downloadArtifact(preview.pbs.filename, preview.pbs.content)}
            >
              download pbs
            </button>
          </div>

          {previewConfigValue && (
            <form className="save-form" onSubmit={(event) => void handleSave(event)}>
              <div className="save-fields">
                <TextField
                  label="artifact directory (server path)"
                  value={artifactDir}
                  onChange={setArtifactDir}
                  placeholder="/scratch/emri/generated"
                />
                <CheckField label="overwrite existing files" value={overwrite} onChange={setOverwrite} />
              </div>
              <button type="submit" className="button" disabled={busy}>
                {busy ? "saving..." : "save to server path"}
              </button>
              {savedPaths.length > 0 && (
                <ul className="saved-paths">
                  {savedPaths.map((path) => <li key={path}><code>{path}</code></li>)}
                </ul>
              )}
            </form>
          )}
        </div>
      )}
    </section>
  );
}
