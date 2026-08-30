import type { RunSummary } from "./types";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "unset";
  if (typeof value === "string") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "unset";
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 6 }).format(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) {
    return value.map((item) => displayValue(item)).join(", ");
  }
  if (isRecord(value)) {
    try {
      return JSON.stringify(value, (_key, item) => (item === null ? "unset" : item));
    } catch {
      return "[object]";
    }
  }
  return String(value);
}

export function formatNumber(value: unknown, digits = 2): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return displayValue(value);
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

export function formatLogDensity(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return displayValue(value);
  return value.toLocaleString("en-US", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
}

export function formatInteger(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return displayValue(value);
  return Math.trunc(value).toLocaleString("en-US");
}

export function formatPercent(finite: unknown, total: unknown): string {
  if (
    typeof finite !== "number" || !Number.isFinite(finite) ||
    typeof total !== "number" || !Number.isFinite(total) || total <= 0
  ) {
    return "unset";
  }
  return `${((finite / total) * 100).toFixed(1)}%`;
}

function basename(value: unknown): string | null {
  if (typeof value !== "string" || !value) return null;
  const normalized = value.replaceAll("\\", "/").replace(/\/+$/, "");
  const parts = normalized.split("/");
  return parts.at(-1) || null;
}

function normalizePath(value: string): string {
  const absolute = value.startsWith("/");
  const output: string[] = [];
  for (const part of value.replaceAll("\\", "/").split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") output.pop();
    else output.push(part);
  }
  return `${absolute ? "/" : ""}${output.join("/")}` || (absolute ? "/" : "");
}

function parentFor(
  run: RunSummary,
  byId: Map<string, RunSummary>,
  byPath: Map<string, RunSummary>,
  byBasename: Map<string, RunSummary>,
): RunSummary | null {
  const pointer = typeof run.from_run === "string" ? run.from_run.trim() : "";
  if (!pointer) return null;
  const byExactId = byId.get(pointer) ?? byId.get(pointer.replace(/^\.\//, ""));
  if (byExactId) return byExactId;

  const pointerPath = normalizePath(pointer);
  const directPath = byPath.get(pointerPath);
  if (directPath) return directPath;

  if (typeof run.path === "string") {
    const parentPath = normalizePath(`${run.path}/../${pointer}`);
    const relativePath = byPath.get(parentPath);
    if (relativePath) return relativePath;
  }

  const pointerBase = basename(pointer);
  return pointerBase ? byBasename.get(pointerBase) ?? null : null;
}

export interface RunGroup {
  key: string;
  label: string;
  runs: RunSummary[];
}

export function groupRunsByChain(runs: RunSummary[]): RunGroup[] {
  const byId = new Map(runs.map((run) => [run.id, run]));
  const byPath = new Map<string, RunSummary>();
  const byBasename = new Map<string, RunSummary>();
  for (const run of runs) {
    if (typeof run.path === "string") byPath.set(normalizePath(run.path), run);
    for (const value of [run.id, run.path, run.out]) {
      const name = basename(value);
      if (name && !byBasename.has(name)) byBasename.set(name, run);
    }
  }

  const rootFor = (start: RunSummary): RunSummary => {
    let current = start;
    const visited = new Set<string>();
    while (!visited.has(current.id)) {
      visited.add(current.id);
      const parent = parentFor(current, byId, byPath, byBasename);
      if (!parent) return current;
      current = parent;
    }
    return current;
  };

  const groups = new Map<string, RunGroup>();
  for (const run of runs) {
    const root = rootFor(run);
    const existing = groups.get(root.id);
    if (existing) existing.runs.push(run);
    else groups.set(root.id, { key: root.id, label: root.id, runs: [run] });
  }
  return [...groups.values()];
}

export function lineageLabel(kind: unknown): string {
  if (kind === "internal_lhs") return "lhs seed";
  if (kind === "from_run") return "from run";
  if (kind === "fixed_point") return "fixed point";
  if (kind === "lhs") return "lhs";
  return displayValue(kind);
}

export function bestProcessStatus(merged: unknown): string {
  if (merged === true) return "merged";
  if (merged === false) return "unmerged";
  if (typeof merged === "string" && merged.trim()) return merged;
  return "unset";
}
