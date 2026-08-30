# FastAPI backend contract

The backend entry point is `backend.api.app:app` (for example,
`uvicorn backend.api.app:app`). It is a same-origin API: the application does
not install CORS middleware and does not add cache headers.

## Run roots and identifiers

The API uses the shipped `backend.emri` root policy. `EMRISEARCH_ROOT` wins over
the primary `backend/config.json` `run_root`; configured `extra_runs` are also
scanned. `GET /api/runs` scans every resolved root, merges results in root order,
and de-duplicates rows by run id or absolute path. A run id is the POSIX
relative path below its root, so nested ids use URL path segments (for example,
`stage_01/replica_a`).

## Endpoints

### `GET /api/runs`

Returns the merged run rail:

```json
{
  "runs": [
    {
      "id": "stage_01",
      "path": "/data/emri/stage_01",
      "kind": "from_run",
      "statistic": "pure",
      "ndim": 5,
      "best_log_density": null,
      "from_run": "../stage_00",
      "out": ".",
      "result_kind": "unset",
      "warnings": []
    }
  ],
  "warnings": []
}
```

The `warnings` array contains scan and per-run warnings; a broken candidate is
skipped rather than aborting the complete scan.

### `GET /api/runs/{id:path}`

Returns a full `RunDetail` display view. Its JSON keys are:

- `summary` — the `RunSummary` object described above;
- `path` and `manifest`;
- `manifest_groups` — grouped `source`, `obs`, `noise`, `modes`, `statistic`,
  `space`, `sampler`, `seeding`, `out`, `emrisearch_version`, and raw manifest
  display data;
- `best` — `log_density`, `search_coordinates`, `physical_coordinates`, and
  per-dimension `dimensions` rows (`name`, `transform`, `search`, `physical`,
  `n_sigma`);
- `diagnostics` — `n_sigma_to_contain` and `best_per_process` tables;
- `samples` — `n_samples` and `n_finite`;
- `warnings`.

The live `result` and `param_space` objects are intentionally absent. See
[Serialization](#serialization) below.

### `GET /api/runs/{id:path}/lineage`

Returns the selected run's known chain, oldest ancestor first and then forward
descendants:

```json
{"chain": [{"id": "stage_00", "path": "...", "kind": "internal_lhs"}]}
```

Lineage uses the data layer's cycle-safe `chain_of` resolution. Pointers may be
absolute paths, relative paths, basenames, or already-relative ids.

### `POST /api/runs`

Request body:

```json
{"path": "/scratch/emri/stage_02"}
```

The path must name an existing directory containing `manifest.json` or
`sampler_state.pkl`. Registration is persisted as an `extra_runs` path by
`register_run_path` and is idempotent.

- **201 Created** — this path was newly added;
- **200 OK** — it was already present;
- **422 Unprocessable Entity** — the path is empty, not a directory, or has
  neither required run marker.

A successful response is the registered `RunSummary` object.

### `GET /api/runs/{id:path}/plots/corner`

Returns `image/png`. Query parameters:

| Parameter | Default | Validation / meaning |
| --- | ---: | --- |
| `top_n` | `10` | Integer, at least `1`; any value is accepted (not snapped to the prototype slider values). |
| `title` | unset | Optional title override. When omitted, the upstream title is used. |
| `annotate` | `true` | Boolean; annotate selected points with their statistic values. |
| `truth` | `true` | Boolean; include the injected truth reference. |
| `theme` | `default` | One of `default`, `dark`, `paper`. |

The renderer enters `matplotlib.pyplot.rc_context` with the accepted theme
recipe. `truth=true` calls upstream
`emrisearch.plotting.corner_plot.plot_result(result, space, top_n, title,
annotate)`. Because that upstream function always draws truth lines, the
`truth=false` branch instead mirrors its body with
`corner_frame(space, title, truth=False)` followed by `overplot(...)`.

### `GET /api/runs/{id:path}/plots/connection`

Returns `image/png`. Query parameters:

| Parameter | Default | Validation / meaning |
| --- | ---: | --- |
| `n` | `81` | Integer, at least `2`; arbitrary values are accepted. |
| `t_range` | `-0.3,1.3` | Exactly two finite comma- or whitespace-separated floats, with high endpoint greater than low endpoint. Parentheses/brackets are also accepted. |
| `ylabel` | unset | Optional y-axis label; upstream default is `statistic`. |
| `progress` | `false` | Boolean passed to the upstream evaluator. |
| `theme` | `default` | One of `default`, `dark`, `paper`. |

The endpoint first attempts to reconstruct an upstream `ParisRun` from the
manifest and bind `run.statistic.bind(run.data)`, then calls upstream
`emrisearch.plotting.connection.connection`. The bound-statistic/waveform stack
is optional and is not a runtime requirement of this API. Any reconstruction,
import, evaluation, or incomplete/non-finite curve failure is caught and
returns a themed labeled placeholder containing:

> connection plot unavailable — bound statistic stack not installed

No synthetic statistic values are generated on that path.

## Errors

All API errors use this shape:

```json
{"detail": "human-readable explanation"}
```

Unknown ids return **404** with exactly
`{"detail": "run not found: <id>"}`. Invalid query/body data and invalid run
markers return **422**.

## Serialization

`backend.api.serialization` lowers display dataclasses with
`dataclasses.asdict` and recursively converts values as follows:

- `numpy.floating` → native `float`;
- `numpy.integer` → native `int`;
- `numpy.bool_` → native `bool`;
- `numpy.ndarray` → nested lists;
- `Path` → `str`;
- tuples (including coordinate tuples) → lists;
- `None` remains JSON `null`;
- the data-layer sentinel string `"unset"` passes through unchanged, so the UI
  can render it as an explicit unavailable value.

`RunDetail.result` and `RunDetail.param_space` are live sampler/space objects,
not API data, and are excluded before serialization. Raw manifest data remains
available under `manifest`; grouped display values retain the data layer's
`"unset"` treatment for null fields.

## Static frontend serving

At import time, if `frontend/dist` exists beside the repository, the app mounts
it at `/` using a `StaticFiles(html=True)` subclass. Missing non-API paths fall
back to `index.html` for Vite/React client-side routing. The API routes are
registered first and remain usable standalone when `frontend/dist` is absent.
