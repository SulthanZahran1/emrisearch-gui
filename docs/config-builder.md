# Config builder and artifact generation

The config builder (issue #14) is a **generate-only** workflow: it validates a
canonical EMRI-C `ParisRun` configuration and renders deterministic, inspectable
Python and PBS artifacts. It never executes generated Python, never submits a
scheduler job, and needs none of the heavy scientific stack.

## Execution boundary (user decision, 2026-08-30)

- No `run.execute()` from the API or UI. The generated Python script calls it
  only when a human later runs the artifact on a compatible node.
- No `qsub`, `sbatch`, scheduler abstraction, background process, status
  polling, logs, monitoring, cancellation, or retries.
- Generation is side-effect free unless the caller explicitly supplies an
  artifact directory.
- Existing files are never overwritten unless `overwrite: true` is explicit.

## Endpoints

### GET /api/configs/canonical

Returns the canonical EMRI-C preset with all defaults explicit:

- `source`: the `emri_c` MOJITO catalogue preset, loaded by the generated
  script via `load_mojito`.
- `obs`: `T=8/12`, `dt=5`, `tdi_gen=1`, `use_gpu=true`, `pad_output=false`.
- `space`: intrinsic `m1, m2, a, p0, e0` with upstream transforms (`log10` for
  the masses, `identity` otherwise) and the stage-1 bounds in search
  coordinates.
- `statistic`: `semicoherent` with `{N_seg: 12}`.
- `noise`: `{add: true, seed: 42}`.
- `modes`: `{ell: 2, n_vals: [-1..5], M_mode: null, N_traj: 5000,
  mode_select: null}`.
- `sampler`: the upstream `SamplerSpec` defaults with explicit values.
- `seeding`: `{kind: internal_lhs, n: 1000, batch_size: 10}`.
- `out`: empty in the preset; a request must supply the run output directory.
- `pbs`: project, job name, walltime, GPU count, CUDA module, venv activation
  path, working directory, log directory, output path, and python filename,
  based on the upstream example `run_emri_c_semicoherent.pbs`.

### POST /api/configs/preview

Request:

```json
{"config": { "...": "canonical config, partial mappings merge with defaults ..." }}
```

Validates and normalizes the configuration, then renders both artifacts in
memory. Never writes files. Response:

```json
{
  "config": {"...": "normalized configuration ..."},
  "artifacts": {
    "python": {"filename": "run_emri_c_semicoherent.py", "content": "..."},
    "pbs": {"filename": "run_emri_c_semicoherent.pbs", "content": "..."}
  },
  "written_paths": [],
  "saved": false
}
```

### POST /api/configs/save

Request:

```json
{
  "config": {"...": "..."},
  "artifact_dir": "/explicit/server/path",
  "overwrite": false
}
```

Validates and renders first, then writes exactly the two artifacts into
`artifact_dir` (created if needed). `overwrite` defaults to `false`; a
collision returns **409** with the existing paths. Unsafe paths (traversal,
NUL/newline, tilde-only, non-directory targets) return **422**. A failed
preflight never leaves a partial pair. Response is the preview shape with
`saved: true` and `written_paths` filled.

## Validation

The pure builder (`backend/emri/config_builder.py`, standard library only)
reports stable field-level errors joined into the API's `{"detail": ...}` 422
shape. Notable rules:

- Unknown nested fields are rejected; nested objects merge with preset defaults.
- `obs.dt` must be at most 10 s (upstream response buffer constraint), `T > 0`,
  `tdi_gen` in `{1, 2}`.
- `space` must be the five intrinsic parameters in order with their upstream
  transforms; `lo < hi` and finite; `fixed` must stay empty for the canonical
  builder.
- `statistic.kind` must be `semicoherent` for now; `N_seg >= 1`.
- `seeding.kind` must be `internal_lhs` for now.
- `exclude_scale_z` accepts the `"inf"` sentinel or a finite non-negative
  number; the generated Python renders `float("inf")`.
- PBS values are narrowly typed (safe module/name/walltime patterns, shell
  quoting for paths); the generated scripts contain no credentials.

## Determinism

The same normalized config always produces identical artifact bytes: stable
key order, fixed Python literals, no timestamps, no random ids, no host
metadata. The generated Python parses with no top-level heavy imports: `few`
and `emrisearch` are imported inside `main()`, and `run.execute()` is called
only under the `if __name__ == "__main__":` guard, so importing the artifact is
inert. The PBS artifact mirrors the upstream example and never invokes
`qsub`/`sbatch`.

## Running the artifacts (human step)

1. Copy the Python and PBS files onto the cluster node next to the configured
   working directory.
2. Review the walltime, project, CUDA module, and venv activation path in the
   PBS file.
3. `qsub run_emri_c_semicoherent.pbs` (PBS) or run the Python directly on a
   GPU node: `EMRISEARCH_OUT=/path python -u run_emri_c_semicoherent.py`.

The run writes `sampler_state.pkl` and `manifest.json` under the configured
output directory, which the results explorer can then scan.
