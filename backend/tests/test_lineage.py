"""Lineage strips, pointer forms, and cycle safety."""

from backend.emri import RunSummary, chain_of, make_run_chain, scan_run_root


def test_three_stage_chain_is_oldest_first_and_middle_includes_descendants(tmp_path):
    paths = make_run_chain(tmp_path / "runs", n_stages=3)
    summaries = scan_run_root(tmp_path / "runs")

    last_chain = chain_of(summaries, "stage_02")
    middle_chain = chain_of(summaries, "stage_01")

    assert [summary.id for summary in last_chain] == ["stage_00", "stage_01", "stage_02"]
    assert [summary.id for summary in middle_chain] == ["stage_00", "stage_01", "stage_02"]
    assert all(summary.path == str(path.resolve()) for summary, path in zip(last_chain, paths))


def test_lineage_accepts_absolute_path_and_basename_pointers(tmp_path):
    root = tmp_path / "runs"
    parent_path = root / "parent"
    child_path = root / "child"
    parent_path.mkdir(parents=True)
    child_path.mkdir(parents=True)
    parent = RunSummary("parent", str(parent_path), out=str(parent_path))
    child = RunSummary("child", str(child_path), from_run="parent", out=str(child_path))
    grandchild = RunSummary(
        "grandchild",
        str(root / "nested" / "grandchild"),
        from_run=str(child_path),
        out=str(root / "nested" / "grandchild"),
    )

    assert [item.id for item in chain_of([parent, child], "child")] == ["parent", "child"]
    assert [item.id for item in chain_of([parent, child, grandchild], "grandchild")] == [
        "parent",
        "child",
        "grandchild",
    ]


def test_lineage_cycle_terminates_with_unique_ids(tmp_path):
    a = RunSummary("a", str(tmp_path / "a"), from_run="b")
    b = RunSummary("b", str(tmp_path / "b"), from_run="a")

    chain = chain_of([a, b], "a")

    ids = [summary.id for summary in chain]
    assert ids == ["b", "a"]
    assert len(ids) == len(set(ids))


def test_missing_lineage_target_does_not_crash_or_invent_a_summary(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    orphan = RunSummary("orphan", str(root / "orphan"), from_run="missing-target")
    unrelated = RunSummary("unrelated", str(root / "unrelated"), from_run="missing-target")

    assert [item.id for item in chain_of([orphan, unrelated], "orphan")] == ["orphan"]
    assert chain_of([orphan], "does-not-exist") == []
