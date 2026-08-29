"""The numpy-only loader remains usable when optional upstream is blocked."""

import sys

import numpy as np
import pytest

from backend.emri import LightRunResult, build_detail, make_manifest_run


STORAGE_KINDS = ("parismc_sampler", "lhs_tuple", "lhs_dict", "npz")


def _block_upstream(monkeypatch):
    for name in list(sys.modules):
        if name == "emrisearch" or name.startswith("emrisearch."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "emrisearch", None)


@pytest.mark.parametrize("kind", STORAGE_KINDS)
def test_forced_fallback_builds_full_detail_without_upstream(tmp_path, monkeypatch, kind):
    run = make_manifest_run(tmp_path / kind, kind=kind, seed=0)
    _block_upstream(monkeypatch)

    detail = build_detail(run, root=tmp_path)

    assert isinstance(detail.result, LightRunResult)
    assert detail.result.kind == kind
    assert detail.result.best_index == 0
    assert detail.best.log_density == pytest.approx(0.0)
    assert detail.n_samples == detail.n_finite == 32
    assert len(detail.best.search_coordinates) == 5
    assert len(detail.best.physical_coordinates) == 5
    assert detail.best.search_coordinates == tuple(detail.param_space.truth_search)
    assert detail.n_sigma_to_contain.available is True
    assert all(row.n_sigma == pytest.approx(0.0) for row in detail.n_sigma_to_contain.rows)


def test_forced_fallback_handles_npz_map_and_keeps_coordinates(tmp_path, monkeypatch):
    run = make_manifest_run(tmp_path / "npz-map", kind="npz", seed=0)
    expected = np.asarray([np.log10(3.0e5), 1.0, 0.3, 12.0, 0.2])
    (run / "sampler_state.pkl").unlink()
    with (run / "sampler_state.pkl").open("wb") as handle:
        np.savez(handle, x_map=expected, lnL_map=np.asarray(0.0))
    _block_upstream(monkeypatch)

    detail = build_detail(run, root=tmp_path)

    assert isinstance(detail.result, LightRunResult)
    assert detail.result.kind == "npz_map"
    np.testing.assert_allclose(detail.best.search_coordinates, expected)
    np.testing.assert_allclose(
        detail.best.physical_coordinates,
        (3.0e5, 10.0, 0.3, 12.0, 0.2),
    )
    assert detail.n_samples == detail.n_finite == 1
