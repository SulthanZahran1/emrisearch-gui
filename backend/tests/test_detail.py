"""Full detail views across all supported storage shapes."""

import json

import numpy as np
import pytest

from backend.emri import UNSET, build_detail, make_legacy_run, make_manifest_run


MANIFEST_KINDS = ("parismc_sampler", "lhs_tuple", "lhs_dict", "npz")


def _truth_search(manifest):
    source = manifest["source"]
    values = []
    for item in manifest["space"]["free"]:
        value = float(source[item["name"]])
        if item["transform"] == "log10":
            value = np.log10(value)
        elif item["transform"] == "cos":
            value = np.cos(value)
        values.append(value)
    return np.asarray(values, dtype=float)


def _physical_truth(manifest):
    source = manifest["source"]
    return tuple(float(source[item["name"]]) for item in manifest["space"]["free"])


@pytest.mark.parametrize("kind", MANIFEST_KINDS)
def test_build_detail_covers_manifest_storage_kinds_and_coordinate_views(tmp_path, kind):
    run = make_manifest_run(tmp_path / kind, kind=kind, seed=0)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))

    detail = build_detail(run, root=tmp_path)

    assert detail.result.kind == kind
    assert detail.result.samples.shape == (32, 5)
    assert detail.result.log_densities.shape == (32,)
    assert detail.result.best_index == 0
    assert detail.best.log_density == pytest.approx(0.0)
    np.testing.assert_allclose(detail.best.search_coordinates, _truth_search(manifest))
    np.testing.assert_allclose(detail.best.physical_coordinates, _physical_truth(manifest))
    assert detail.samples.n_samples == detail.n_samples == 32
    assert detail.samples.n_finite == detail.n_finite == 32
    assert detail.summary.path == str(run.resolve())
    assert detail.summary.ndim == 5
    assert detail.ndim == 5

    expected_dimensions = []
    for item in manifest["space"]["free"]:
        transform = item["transform"]
        prefix = "log10_" if transform == "log10" else "cos_" if transform == "cos" else ""
        expected_dimensions.append(
            (item["name"], transform, item["lo"], item["hi"], prefix + item["name"])
        )
    actual_dimensions = [
        (row.name, row.transform, row.lo, row.hi, row.search_coord)
        for row in detail.search_space.rows
    ]
    assert actual_dimensions == expected_dimensions
    assert [row.name for row in detail.best.dimensions] == [item[0] for item in expected_dimensions]
    assert [row.transform for row in detail.best.dimensions] == [item[1] for item in expected_dimensions]
    assert all(row.n_sigma == pytest.approx(0.0) for row in detail.best.dimensions)

    groups = detail.manifest_groups
    assert set(detail.manifest) >= {
        "emrisearch_version",
        "source",
        "obs",
        "noise",
        "modes",
        "statistic",
        "space",
        "sampler",
        "seeding",
        "out",
    }
    assert groups.emrisearch_version == "0.1.0"
    for name in ("source", "obs", "noise", "modes", "statistic", "sampler", "seeding"):
        assert getattr(groups, name)
    assert groups.space is groups.search_space
    assert groups.out == manifest["out"]
    assert groups.raw == manifest

    if kind == "parismc_sampler":
        assert detail.best_per_process.available is True
        assert len(detail.best_per_process.rows) == 4
    else:
        assert detail.best_per_process.available is False
        assert detail.best_per_process.rows == ()


def test_build_detail_supports_the_npz_map_storage_shape(tmp_path):
    run = make_manifest_run(tmp_path / "npz-map", kind="npz", seed=0)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    truth = _truth_search(manifest)
    (run / "sampler_state.pkl").unlink()
    with (run / "sampler_state.pkl").open("wb") as handle:
        np.savez(handle, x_map=truth, lnL_map=np.asarray(0.0))

    detail = build_detail(run, root=tmp_path)

    assert detail.result.kind == "npz_map"
    assert detail.result.best_index == 0
    assert detail.best.log_density == pytest.approx(0.0)
    np.testing.assert_allclose(detail.best.search_coordinates, truth)
    np.testing.assert_allclose(detail.best.physical_coordinates, _physical_truth(manifest))
    assert detail.n_samples == detail.n_finite == 1
    assert detail.best_per_process.available is False


@pytest.mark.parametrize("kind", ("parismc_sampler", "lhs_tuple", "lhs_dict", "npz"))
def test_build_detail_handles_legacy_state_only_runs(tmp_path, kind):
    run = make_legacy_run(tmp_path / kind, kind=kind, seed=0)
    expected_search = np.asarray([np.log10(3.0e5), 1.0, 0.3, 12.0, 0.2])

    detail = build_detail(run, root=tmp_path)

    assert detail.manifest == {}
    assert detail.summary.kind == "legacy"
    assert detail.result.kind == kind
    assert detail.best.log_density == pytest.approx(0.0)
    np.testing.assert_allclose(detail.best.search_coordinates, expected_search)
    np.testing.assert_allclose(detail.best.physical_coordinates, expected_search)
    assert detail.n_samples == detail.n_finite == 32
    if kind == "parismc_sampler":
        assert detail.best_per_process.available is True
        assert len(detail.best_per_process.rows) == 4
    else:
        assert detail.best_per_process.available is False
        assert detail.best_per_process.rows == ()
    assert len(detail.n_sigma_to_contain.rows) == 5
    assert all(row.truth == UNSET and row.n_sigma == UNSET for row in detail.n_sigma_to_contain.rows)


def test_manifest_only_detail_has_empty_counts_and_unset_diagnostics(tmp_path):
    # build_detail returns an empty result for a manifest-backed directory
    # with no state file (upstream permits manifest-only stages: the manifest
    # is written before and after execution, run.py:408/433).
    run = make_manifest_run(tmp_path / "manifest-only", kind="lhs_tuple", seed=0)
    (run / "sampler_state.pkl").unlink()

    detail = build_detail(run, root=tmp_path)

    assert detail.n_samples == detail.n_finite == 0
    assert detail.best.log_density is None
    # Diagnostics keep the per-dimension table shape (docs/data-layer.md):
    # rows mirror the 5 free dimensions, all values "unset" with no sigma.
    assert detail.diagnostics.n_sigma_to_contain.rows
    assert len(detail.diagnostics.n_sigma_to_contain.rows) == 5
    assert all(row.sigma == UNSET and row.n_sigma == UNSET for row in detail.diagnostics.n_sigma_to_contain.rows)
    assert detail.diagnostics.best_per_process.status == UNSET
