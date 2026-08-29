"""GUI diagnostic formulas and process-agreement reads."""

import json
import pickle

import numpy as np
import pytest

from backend.emri import (
    LightRunResult,
    UNSET,
    best_per_process,
    build_detail,
    make_legacy_run,
    make_manifest_run,
    n_sigma_to_contain,
)


def _physical_from_search(space, search):
    values = []
    for param, value in zip(space.free, search):
        if param.transform == "log10":
            values.append(10.0 ** float(value))
        elif param.transform == "cos":
            values.append(float(np.arccos(value)))
        else:
            values.append(float(value))
    return tuple(values)


def test_n_sigma_to_contain_matches_independent_covariance_formula(tmp_path):
    run = make_manifest_run(tmp_path / "paris", kind="parismc_sampler", seed=0)
    detail = build_detail(run, root=tmp_path)
    table = detail.diagnostics.n_sigma_to_contain

    samples = np.asarray(detail.result.finite().samples, dtype=float)
    covariance = np.cov(samples, rowvar=False, ddof=1)
    expected_sigma = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    expected_truth = np.asarray(detail.param_space.truth_search, dtype=float)
    expected_best = np.asarray(detail.best.search_coordinates, dtype=float)

    assert table.available is True
    assert len(table.rows) == detail.param_space.ndim
    for index, row in enumerate(table.rows):
        assert row.name == detail.param_space.free[index].name
        assert row.best == pytest.approx(expected_best[index])
        assert row.truth == pytest.approx(expected_truth[index])
        assert row.sigma == pytest.approx(expected_sigma[index])
        expected_n_sigma = max(
            0.0,
            abs(expected_best[index] - expected_truth[index]) / expected_sigma[index],
        )
        assert row.n_sigma == pytest.approx(expected_n_sigma)
        assert row.n_sigma == pytest.approx(0.0, abs=1e-12)


def test_n_sigma_unavailable_covariance_and_legacy_truth_use_unset_sentinel(tmp_path):
    manifest_run = make_manifest_run(tmp_path / "manifest", kind="lhs_tuple", seed=0)
    manifest = json.loads((manifest_run / "manifest.json").read_text(encoding="utf-8"))
    detail = build_detail(manifest_run, root=tmp_path)
    one_sample = LightRunResult(
        np.asarray([detail.best.search_coordinates]),
        np.asarray([0.0]),
        manifest=manifest,
    )

    unavailable = n_sigma_to_contain(one_sample, space=detail.param_space)

    assert unavailable.available is False
    assert len(unavailable.rows) == detail.param_space.ndim
    assert all(row.sigma == UNSET and row.n_sigma == UNSET for row in unavailable.rows)

    legacy = build_detail(make_legacy_run(tmp_path / "legacy", kind="lhs_tuple", seed=0), root=tmp_path)
    assert all(row.truth == UNSET and row.n_sigma == UNSET for row in legacy.n_sigma_to_contain.rows)


def test_best_per_process_reports_four_merged_rows_and_coordinate_views(tmp_path):
    run = make_manifest_run(tmp_path / "paris", kind="parismc_sampler", seed=0)
    detail = build_detail(run, root=tmp_path)

    table = best_per_process(detail.result, space=detail.param_space)

    assert table.available is True
    assert [row.process for row in table.rows] == [0, 1, 2, 3]
    assert table.status == "merged"
    assert table.spread < 5.0
    assert all(row.log_density != UNSET for row in table.rows)
    for row in table.rows:
        assert len(row.search_coordinates) == detail.param_space.ndim
        assert len(row.physical_coordinates) == detail.param_space.ndim
        np.testing.assert_allclose(
            row.physical_coordinates,
            _physical_from_search(detail.param_space, row.search_coordinates),
        )


def test_best_per_process_uses_unmerged_threshold_at_spread_five(tmp_path):
    run = make_manifest_run(tmp_path / "paris", kind="parismc_sampler", seed=0)
    detail = build_detail(run, root=tmp_path)
    with (run / "sampler_state.pkl").open("rb") as handle:
        sampler = pickle.load(handle)

    points = [np.asarray(part[:1], dtype=float) for part in sampler.searched_points_list]
    sampler.element_num_list = [1, 1, 1, 1]
    sampler.searched_points_list = points
    sampler.searched_log_densities_list = [
        np.asarray([0.0]),
        np.asarray([-5.0]),
        np.asarray([-2.0]),
        np.asarray([-1.0]),
    ]

    table = best_per_process(sampler, space=detail.param_space)

    assert table.available is True
    assert len(table.rows) == 4
    assert table.spread == pytest.approx(5.0)
    assert table.merged is False
    assert table.status == table.read == "unmerged"
    for row in table.rows:
        assert len(row.search_coordinates) == 5
        assert len(row.physical_coordinates) == 5


def test_non_process_result_has_unavailable_process_table(tmp_path):
    run = make_manifest_run(tmp_path / "lhs", kind="lhs_tuple", seed=0)
    detail = build_detail(run, root=tmp_path)

    table = best_per_process(detail.result, space=detail.param_space)

    assert table.available is False
    assert table.rows == ()
    assert table.spread == UNSET
    assert table.status == table.read == UNSET
