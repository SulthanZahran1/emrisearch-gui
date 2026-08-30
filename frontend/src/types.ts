export type JsonValue = unknown;
export type UnknownRecord = Record<string, unknown>;

export interface RunSummary {
  id: string;
  path: string;
  kind: string | null;
  statistic: string | null;
  ndim: number | null;
  best_log_density: number | null;
  from_run: string | null;
  out: string | null;
  result_kind: string | null;
  warnings?: string[];
}

export interface RunsResponse {
  runs: RunSummary[];
  warnings: string[];
}

export interface SearchDimension {
  name: string;
  transform: string;
  search_coord?: string;
  lo: JsonValue;
  hi: JsonValue;
}

export interface SearchSpace {
  dimensions?: SearchDimension[];
  fixed?: UnknownRecord;
  truth?: UnknownRecord;
}

export interface ManifestGroups {
  emrisearch_version?: JsonValue;
  source?: UnknownRecord;
  obs?: UnknownRecord;
  noise?: UnknownRecord;
  modes?: UnknownRecord;
  statistic?: UnknownRecord;
  space?: SearchSpace;
  sampler?: UnknownRecord;
  seeding?: UnknownRecord;
  out?: JsonValue;
  raw?: UnknownRecord;
  [key: string]: JsonValue;
}

export interface BestDimension {
  name: string;
  transform: string;
  search: JsonValue;
  physical: JsonValue;
  n_sigma: JsonValue;
}

export interface BestPoint {
  log_density: number | null;
  search_coordinates?: JsonValue[];
  physical_coordinates?: JsonValue[];
  dimensions?: BestDimension[];
}

export interface NSigmaRow {
  name: string;
  best: JsonValue;
  truth: JsonValue;
  sigma: JsonValue;
  n_sigma: JsonValue;
}

export interface NSigmaTable {
  rows?: NSigmaRow[];
  available?: boolean;
}

export interface ProcessBest {
  process: number;
  log_density: JsonValue;
  search_coordinates?: JsonValue[];
  physical_coordinates?: JsonValue[];
}

export interface BestPerProcessTable {
  rows?: ProcessBest[];
  spread?: JsonValue;
  merged?: boolean | null | string;
  available?: boolean;
}

export interface Diagnostics {
  n_sigma_to_contain?: NSigmaTable;
  best_per_process?: BestPerProcessTable;
}

export interface SampleCounts {
  n_samples?: JsonValue;
  n_finite?: JsonValue;
}

export interface LineageItem {
  id: string;
  path: string;
  kind: string | null;
}

export interface LineageResponse {
  chain: LineageItem[];
}

export interface RunDetail {
  summary: RunSummary;
  path: JsonValue;
  manifest: UnknownRecord;
  manifest_groups: ManifestGroups;
  best: BestPoint;
  diagnostics: Diagnostics;
  samples: SampleCounts;
  warnings: string[];
}
