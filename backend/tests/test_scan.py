"""Recursive run discovery and warning isolation."""

import json

from backend.emri import (
    get_scan_warnings,
    make_legacy_run,
    make_manifest_run,
    scan_run_root,
)


def test_scan_discovers_nested_manifest_and_legacy_runs_sorted_by_absolute_path(tmp_path):
    root = tmp_path / "runs"
    first = make_manifest_run(root / "alpha", kind="lhs_tuple", seed=0)
    nested = make_manifest_run(root / "nested" / "deep" / "beta", kind="lhs_dict", seed=1)
    legacy = make_legacy_run(root / "legacy", kind="lhs_tuple", seed=2)
    (root / "not-a-run").mkdir(parents=True)
    (root / "not-a-run" / "notes.txt").write_text("not a run", encoding="utf-8")

    summaries = scan_run_root(root)

    expected_paths = sorted(str(path.resolve()) for path in (first, nested, legacy))
    assert [summary.path for summary in summaries] == expected_paths
    assert [summary.id for summary in summaries] == [
        "alpha",
        "legacy",
        "nested/deep/beta",
    ]
    assert get_scan_warnings() == ()
    assert scan_run_root.warnings == ()


def test_scan_does_not_follow_symlinked_directories(tmp_path):
    root = tmp_path / "runs"
    outside = tmp_path / "outside"
    external_run = make_manifest_run(outside / "external", kind="lhs_tuple", seed=0)
    root.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        # Symlink creation is unavailable on a few restricted filesystems; the
        # ordinary discovery tests still cover the candidate walk.
        return

    summaries = scan_run_root(root)

    assert summaries == []
    assert str(external_run.resolve()) not in {summary.path for summary in summaries}


def test_broken_candidates_are_skipped_and_warnings_are_published(tmp_path):
    root = tmp_path / "runs"
    good = make_manifest_run(root / "good", kind="lhs_tuple", seed=0)
    invalid_json = root / "broken-json"
    invalid_json.mkdir(parents=True)
    (invalid_json / "manifest.json").write_text("{not json", encoding="utf-8")
    non_object = root / "broken-shape"
    non_object.mkdir(parents=True)
    (non_object / "manifest.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    summaries = scan_run_root(root)

    assert [summary.path for summary in summaries] == [str(good.resolve())]
    warnings = get_scan_warnings()
    assert scan_run_root.warnings == warnings
    assert len(warnings) == 2
    assert any(str(invalid_json.resolve()) in warning for warning in warnings)
    assert any(str(non_object.resolve()) in warning for warning in warnings)
    assert all("skipping broken run" in warning for warning in warnings)


def test_scan_missing_or_non_directory_root_returns_warning(tmp_path):
    missing = tmp_path / "does-not-exist"

    assert scan_run_root(missing) == []
    warnings = get_scan_warnings()
    assert len(warnings) == 1
    assert "not a readable directory" in warnings[0]
    assert str(missing.resolve()) in warnings[0]
