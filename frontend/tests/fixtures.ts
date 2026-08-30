import type { LineageItem, RunDetail, RunSummary } from "../src/types";

export function makeSummary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    id: "stage_00",
    path: "/tmp/emri/stage_00",
    kind: "internal_lhs",
    statistic: "f_pure",
    ndim: 2,
    best_log_density: -10.5,
    from_run: null,
    out: ".",
    result_kind: "parismc_sampler",
    warnings: [],
    ...overrides,
  };
}

export function makeDetail(
  id = "stage_00",
  overrides: Partial<RunDetail> = {},
): RunDetail {
  const summary = makeSummary({
    id,
    path: `/tmp/emri/${id}`,
    ...overrides.summary,
  });
  return {
    summary,
    path: summary.path,
    manifest: {
      source: { m1: 300000, absent_source_value: null },
      obs: { T: 0.5, T_margin: null },
      statistic: { kind: "f_pure", N_seg: null },
      space: { free: [] },
      seeding: { kind: summary.kind },
    },
    manifest_groups: {
      emrisearch_version: "0.1.0",
      source: { m1: 300000, absent_source_value: null },
      obs: { T: 0.5, T_margin: null },
      noise: { add: true, seed: 7 },
      modes: { ell: 2, n_vals: [1, 2, 3] },
      statistic: { kind: "f_pure", N_seg: null },
      space: {
        dimensions: [
          { name: "m1", transform: "log10", search_coord: "log10_m1", lo: 5, hi: 6 },
          { name: "a", transform: "identity", search_coord: "a", lo: 0, hi: 0.9 },
        ],
        fixed: { dist: null },
        truth: { m1: 300000, a: 0.3 },
      },
      sampler: { n_seed: 32, stop_dlogZ: null },
      seeding: { kind: summary.kind, path: summary.from_run },
      out: summary.out,
      raw: {},
    },
    best: {
      log_density: -10.5,
      search_coordinates: [5.48, 0.31],
      physical_coordinates: [300000, 0.31],
      dimensions: [
        { name: "m1", transform: "log10", search: 5.48, physical: 300000, n_sigma: 0.4 },
        { name: "a", transform: "identity", search: 0.31, physical: 0.31, n_sigma: 1.2 },
      ],
    },
    diagnostics: {
      n_sigma_to_contain: {
        available: true,
        rows: [{ name: "m1", best: 5.48, truth: 5.477, sigma: 0.01, n_sigma: 0.4 }],
      },
      best_per_process: {
        available: true,
        rows: [{ process: 0, log_density: -10.5, search_coordinates: [5.48, 0.31], physical_coordinates: [300000, 0.31] }],
        spread: 0.2,
        merged: null,
      },
    },
    samples: { n_samples: 32, n_finite: 31 },
    warnings: [],
    ...overrides,
    summary,
    path: overrides.path ?? summary.path,
  };
}

export function makeLineage(ids: string[]): LineageItem[] {
  return ids.map((id, index) => ({
    id,
    path: `/tmp/emri/${id}`,
    kind: index === 0 ? "internal_lhs" : "from_run",
  }));
}

export function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
