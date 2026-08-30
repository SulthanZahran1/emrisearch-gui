import { describe, expect, it } from "vitest";
import { bestProcessStatus, displayValue, groupRunsByChain } from "../src/format";
import { makeSummary } from "./fixtures";

describe("display formatting and chain grouping", () => {
  it("renders missing, null, and non-finite values as visible unset", () => {
    expect(displayValue(null)).toBe("unset");
    expect(displayValue(undefined)).toBe("unset");
    expect(displayValue(Number.NaN)).toBe("unset");
    expect(displayValue({ optional: null })).toBe('{"optional":"unset"}');
    expect(bestProcessStatus(null)).toBe("unset");
  });

  it("groups transitive from_run pointers without merging an unrelated chain", () => {
    const runs = [
      makeSummary({ id: "stage_00", path: "/runs/stage_00", from_run: null }),
      makeSummary({ id: "stage_01", path: "/runs/stage_01", from_run: "../stage_00", kind: "from_run" }),
      makeSummary({ id: "stage_01/replica a", path: "/runs/stage_01/replica a", from_run: "../stage_01", kind: "from_run" }),
      makeSummary({ id: "independent", path: "/runs/independent", from_run: null, kind: "internal_lhs" }),
    ];

    const groups = groupRunsByChain(runs);

    expect(groups).toHaveLength(2);
    expect(groups.map((group) => group.key)).toEqual(["stage_00", "independent"]);
    expect(groups[0].runs.map((run) => run.id)).toEqual([
      "stage_00",
      "stage_01",
      "stage_01/replica a",
    ]);
    expect(groups[1].runs.map((run) => run.id)).toEqual(["independent"]);
  });

  it("keeps a cyclic pointer bounded and assigns the cycle to its first root", () => {
    const groups = groupRunsByChain([
      makeSummary({ id: "a", path: "/runs/a", from_run: "b" }),
      makeSummary({ id: "b", path: "/runs/b", from_run: "a" }),
    ]);

    const ids = groups.flatMap((group) => group.runs.map((run) => run.id));
    expect(ids.sort()).toEqual(["a", "b"]);
    expect(new Set(ids)).toEqual(new Set(["a", "b"]));
  });
});
