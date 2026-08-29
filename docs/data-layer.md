# Results explorer data layer

The `backend/emri` package is the local-first read model for the results
explorer. It reads an upstream `manifest.json` plus sampler state, but it does
not run a search and it does not make plotting or FastAPI dependencies part of
the GUI install.

## Module map

| Module | Public purpose |
| --- | --- |
| `types.py` | Frozen dataclasses for run rows, detail views, diagnostic tables, and plot requests. |
| `root.py` | Option-A root resolution and persistent add-run configuration. |
| `scan.py` | Recursive discovery of directories containing a manifest or state file. |
| `summary.py` | Manifest-only fast summaries and cheap legacy tuple/dict/NPZ summaries. |
| `detail.py` | Optional upstream result loading, numpy-only fallback loading, coordinate views, and diagnostics. |
| `plots.py` | Pure request builders for the future server-side PNG endpoint. |
| `lineage.py` | Cycle-safe ancestor/descendant strip construction. |
| `fixtures.py` | Deterministic run directories for tests and smoke scripts; never imports the heavy stack. |

The package exports the most commonly used functions from `emri.__init__`:

```python
load_config(path=None) -> dict
save_config(config, path=None) -> dict
resolve_run_root(config_path=None) -> Path | None
resolve_run_roots(config_path=None) -> tuple[Path, ...]
register_run_path(path, config_path=None) -> dict
scan_run_root(root) -> list[RunSummary]
summarize_run(path, root=None) -> RunSummary
build_detail(path, root=None) -> RunDetail
chain_of(run_summaries, start_id) -> list[RunSummary]
corner_request(detail, top_n=10, title=None, truth=True, theme="default") -> PlotRequest
connection_request(detail, n=81, t_range=(-0.3, 1.3), ylabel=None, progress=False) -> PlotRequest
```

The pure diagnostic helpers are also public:

```python
n_sigma_to_contain(result, space=None, truth=None, best=None) -> NSigmaTable
best_per_process(sampler_or_result, space=None) -> BestPerProcessTable
```

## Core view types

`RunSummary` is the run-rail row. It contains `id`, absolute `path`, seeding
`kind`, statistic name, `ndim`, optional `best_log_density`, optional
`from_run`, `out`, and `result_kind`. For a manifest-backed run, `kind` is the
manifest seeding kind (`internal_lhs`, `lhs`, `fixed_point`, or `from_run`). A
state-only run is deliberately `kind="legacy"`; `result_kind` is only filled
when its inexpensive shape can be identified.

`RunDetail` contains the raw manifest, a grouped `ManifestDetails` view, a
`BestPoint`, `Diagnostics`, `SampleCounts`, the loaded result, and the
numpy-only `LightParamSpace` used for conversions. `ManifestDetails` groups the
accepted prototype vocabulary:

- `source`
- `obs`, `noise`, `modes` (also available as flattened
  `observation_noise_modes`)
- `statistic`
- `space` / `search_space`, whose rows are `SearchDimension(name, transform,
  lo, hi, search_coord)`
- fixed parameters
- `sampler`
- `seeding`
- `out`
- `emrisearch_version`

The raw manifest is not rewritten or augmented. In the display view, JSON
`null` values become the string sentinel `"unset"`; absent mapping groups stay
empty so the renderer does not invent field names.

`BestPoint` exposes the best log-density and tuples of search and physical
coordinates. Its `dimensions` rows carry `name`, `transform`, `search`,
`physical`, and `n_sigma`. The search coordinate convention is the upstream
one: `log10_m1`, `log10_m2`, `cos_qS`, etc.; `lo` and `hi` remain in search
coordinates.

`Diagnostics` has two tables. `NSigmaTable.rows` are `NSigmaRow` values, and
`BestPerProcessTable.rows` are `ProcessBest` values. The latter also has
`spread`, `merged`, and `status`/`read` (`"merged"`, `"unmerged"`, or
`"unset"`). `SampleCounts` provides `n_samples` and `n_finite`.

## Root-resolution contract (option A)

`resolve_run_root()` first checks the non-empty `EMRISEARCH_ROOT` environment
variable. If present, it returns that path and ignores the config file. If the
environment variable is absent, the optional `backend/config.json` is read:

```json
{
  "run_root": "/data/emri-runs",
  "extra_runs": ["/scratch/another-run", "/tmp/demo-run"]
}
```

A missing config is valid and means no primary root. `resolve_run_roots()`
returns the primary root followed by persistent `extra_runs`, de-duplicated in
order. `resolve_run_root()` itself returns only the primary root because its
name is singular; callers that want the complete run listing should scan
`resolve_run_roots()`.

`register_run_path(path)` resolves and appends a path to `extra_runs` in the
same `backend/config.json` (or the explicitly supplied config path). It is
idempotent. `load_config()` and `save_config()` use one process-local
re-entrant lock; writes use a temporary file and `os.replace`. This is
thread-safe enough for the single-process backend, not a multi-process or
network configuration store.

## Discovery and the pickle boundary

`scan_run_root(root)` uses `os.walk` without following symlinked directories.
A candidate directory contains `manifest.json` or `sampler_state.pkl`; each
candidate is summarized, sorted by absolute path, and returned. Directory walk
errors and broken candidates are skipped and collected in
`get_scan_warnings()` / `scan_run_root.warnings`.

`summarize_run(path, root=None)` has a strict fast path: when a manifest exists
it reads JSON only and never opens or stats the pickle. It obtains seeding kind,
statistic, dimension count, lineage pointer, and output path from the
manifest. If a future writer stores an optional best value in the JSON, the
summary reads it without opening state.

Without a manifest, the summary labels the run `legacy`. It can cheaply read
an ordinary pickle containing one of upstream's LHS tuple/dict shapes, or an
NPZ container (including the fixture's `sampler_state.pkl` ZIP-shaped file), to
obtain dimension count and a finite best value. A pickle with the `parismc`
marker is not deserialized on this path; its best value belongs to the detail
view. This keeps large or callable-dependent sampler state out of directory
scans.

## Detail loading and coordinates

`detail.load_result()` first tries `emrisearch.io.load_run(..., stubs=True)`
when the optional upstream package is importable. Any optional import/runtime
failure falls back to `LightRunResult`, which mirrors the useful upstream
shapes:

- `parismc_sampler`: sampler state with `get_samples_with_weights`, or its
  per-process searched lists;
- `lhs_tuple`: `(points, values)`;
- `lhs_dict`: `lhs_phys`/`log_densities`, `phys_pts`/`det_snr`, or
  `samples`/`log_densities`;
- `npz` with the corresponding arrays;
- `npz_map` with `x_map` and optional `lnL_map`.

The fallback has `best`, `best_index`, `finite()`, `top(n)`,
`posterior_covariance()`, and `param_space()` helpers. Per-process searched
points are treated as unit-cube values and passed to
`apply_prior_transform(points, prior_transform)`, just as upstream does.

Physical conversion follows the canonical upstream transform table:

- `log10`: `search = log10(physical)`, `physical = 10**search`;
- `cos`: `search = cos(physical)`, `physical = arccos(search)`;
- `identity`: unchanged.

The canonical physical parameter order is
`m1, m2, a, p0, e0, xI0, dist, qS, phiS, qK, phiK, Phi_phi0,
Phi_theta0, Phi_r0`. The detail table only shows free dimensions; fixed values
remain in the manifest search-space group.

## GUI-side diagnostics

These two names intentionally belong to the GUI data layer. A source search
can display them, but upstream has no API with either name.

### `n_sigma_to_contain`

For each free dimension `i`:

```text
sigma_i = sqrt(max(posterior_covariance(result).diagonal()[i], 0))
n_sigma_i = max(0, abs(best_search_i - truth_search_i) / sigma_i)
```

`truth_search` is obtained from `manifest["space"]["truth"]` using the same
per-parameter transform as the search space. The covariance is calculated on
finite samples. If covariance, truth, best, or a positive finite sigma is
unavailable, the row's `sigma` and/or `n_sigma` is `"unset"`. The absolute
value and clamp are deliberate: this is a containment distance, not a signed
residual. The prototype flags values above 2 in its renderer, but the data
layer does not discard or threshold rows.

### `best_per_process`

This table is produced only when all of the following sampler attributes are
available: `n_proc`, `element_num_list`, `searched_points_list`,
`searched_log_densities_list`, `prior_transform`, and
`apply_prior_transform`. For process `j`, only its first
`element_num_list[j]` entries are read; the maximum finite log-density and its
unit-cube point are selected, then the point is mapped to search coordinates
with the upstream prior-transform call. The table carries both search and
physical coordinates when a space is available.

The process agreement read uses the prototype's threshold:

```text
spread = max(process_best_log_densities) - min(process_best_log_densities)
merged = spread < 5.0
```

Thus `status` is `merged` for a spread below 5, `unmerged` otherwise, and
`unset` when no numeric process best exists. LHS/NPZ/other non-process shapes
return an unavailable table instead of pretending that one global best is a
process diagnostic.

## Plot requests

The builders never import matplotlib, corner, or a waveform/statistic stack.
They create `PlotRequest` objects whose `kwargs` contain only arguments
accepted by the upstream call.

`corner_request()` targets
`emrisearch.plotting.corner_plot.plot_result` and carries:

```python
{
    "result": detail.result,
    "space": detail.param_space,
    "top_n": top_n,
    "title": title,
    "annotate": True,
}
```

The GUI-only `truth` and `theme` values stay in request metadata. Upstream
`plot_result` has no truth or theme argument; its frame draws truth by default,
so a future endpoint can post-process the truth lines and apply a matplotlib
rcParams theme.

`connection_request()` targets
`emrisearch.plotting.connection.connection` and carries:

```python
{
    "f": None,                 # endpoint binds the heavy bound statistic
    "a": tuple(detail.param_space.truth_search),
    "b": tuple(detail.best.search_coordinates),
    "t_range": tuple(t_range),
    "n": n,
    "space": detail.param_space,
    "labels": ("injection", "recovered"),
    "ylabel": ylabel or "statistic",
    "title": None,
    "progress": progress,
}
```

`a` and `b` are intentionally search coordinates: upstream's `connection`
evaluator calls `space.to_physical()` before evaluating the bound statistic.
`PlotTheme` is the enum `default | dark | paper`.

## Fixture strategy

`fixtures.make_manifest_run(directory, kind, seed)` writes a real-shape
manifest with all fields emitted by the current upstream `ParisRun.manifest`
and a small state with 32 deterministic points. Supported state shapes are
`parismc_sampler`, `lhs_tuple`, `lhs_dict`, and `npz`. The fake sampler is a
plain pickleable object with the upstream duck-typed methods and per-process
unit-cube arrays; it never imports `parismc`. The NPZ fixture is written to the
upstream state filename while retaining ZIP magic, so directory discovery sees
it and the local loader still recognizes its `npz` shape.

`make_legacy_run()` writes a state-only run with no manifest. `make_run_chain`
creates `stage_00`, `stage_01`, ... and patches later manifests to use
relative `from_run` pointers. All random values come from
`numpy.random.default_rng(seed)` and the first point is the known truth, so
same-seed fixtures are reproducible and diagnostics have a stable optimum.

The module itself depends only on numpy plus the Python standard library. It
must remain importable without `emrisearch`, `parismc`, corner, matplotlib,
FastEMRIWaveforms, lisatools, or FastLISAResponse.

## Upstream contract citations

The implementation follows the read/write contract verified in the upstream
clone (`/home/dev/emrisearch/src/emrisearch`):

- `io.py:30-31` names `manifest.json` and `sampler_state.pkl`.
- `io.py:152-158` reads an optional manifest; `io.py:161-172` recognizes run
  directories; `io.py:174-203` covers bare pickles, LHS tuples, and LHS dicts.
- `io.py:206-252` extracts a sampler, preferring
  `get_samples_with_weights` and then concatenating the first
  `element_num_list[j]` entries from each process, with the unit-cube prior
  transform. `io.py:255-267` covers NPZ and `npz_map` shapes.
- `io.py:34-118` defines `RunResult`'s normalized arrays, `best`, `finite`,
  `top`, manifest parameter-space reconstruction, and weighted covariance.
- `run.py:104-245` defines the seeding kinds and `from_run` pointer shape;
  `run.py:317-332` emits the manifest fields `emrisearch_version`, `source`,
  `obs`, `noise`, `modes`, `statistic`, `space`, `sampler`, `seeding`, and
  `out`.
- `config.py:57-59` defines `ObsConfig.to_manifest`, `config.py:99-109`
  defines `ModeConfig.to_manifest`, and `config.py:171-186` defines the
  sampler manifest serialization.
- `params.py:22-27` gives the physical parameter order;
  `params.py:132-188` defines `log10`, `cos`, and `identity` transforms; and
  `params.py:440-453` defines the `free`/`truth`/`fixed` search-space manifest
  shape.
- `plotting/connection.py:86-92` defines the `connection(f, a, b, t_range,
  n, space, labels, ylabel, title, progress)` signature.
- `plotting/corner_plot.py:130-157` defines `plot_result(result, space,
  top_n, title, annotate)`; the absence of a truth/theme parameter is why
  those controls remain GUI metadata in `PlotRequest`.
