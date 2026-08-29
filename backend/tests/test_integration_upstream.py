"""Optional integration checks against the installed upstream loader."""

import pickle

import numpy as np
import pytest

from backend.emri import LightRunResult, load_result, make_manifest_run


@pytest.fixture
def upstream_load_run():
    pytest.importorskip("emrisearch")
    from emrisearch.io import load_run

    return load_run


def test_upstream_parismc_directory_maps_unit_cube_points(upstream_load_run, tmp_path):
    run = make_manifest_run(tmp_path / "paris", kind="parismc_sampler", seed=0)
    with (run / "sampler_state.pkl").open("rb") as handle:
        sampler = pickle.load(handle)
    unit_points = np.concatenate(
        [
            np.asarray(points[:count], dtype=float)
            for points, count in zip(
                sampler.searched_points_list, sampler.element_num_list
            )
        ],
        axis=0,
    )
    expected_search = np.asarray(
        sampler.apply_prior_transform(unit_points, sampler.prior_transform), dtype=float
    )

    result = upstream_load_run(str(run), stubs=True)

    assert result.kind == "parismc_sampler"
    assert result.samples.shape == (32, 5)
    assert result.log_densities.shape == (32,)
    np.testing.assert_allclose(result.samples, expected_search)
    np.testing.assert_allclose(result.log_densities, sampler._log_densities)
    assert result.sampler is not None


def test_upstream_lhs_tuple_state_file_has_legacy_kind(upstream_load_run, tmp_path):
    run = make_manifest_run(tmp_path / "lhs", kind="lhs_tuple", seed=0)

    # Upstream's file-level legacy branch recognizes this shape.  The separate
    # directory-level behavior is pinned below because load_run treats every
    # directory as a PARIS sampler directory first.
    result = upstream_load_run(str(run / "sampler_state.pkl"), stubs=True)

    assert result.kind == "lhs_tuple"
    assert result.samples.shape == (32, 5)
    assert result.log_densities.shape == (32,)


@pytest.mark.xfail(
    reason=(
        "upstream io.load_run currently treats a directory as a sampler state "
        "and cannot classify a legacy tuple stored inside it"
    ),
    strict=False,
)
def test_upstream_lhs_tuple_fixture_directory_has_legacy_kind(upstream_load_run, tmp_path):
    run = make_manifest_run(tmp_path / "lhs-directory", kind="lhs_tuple", seed=0)

    result = upstream_load_run(str(run), stubs=True)

    assert result.kind == "lhs_tuple"


def test_upstream_npz_directory_diverges_from_gui_light_loader(upstream_load_run, tmp_path):
    run = make_manifest_run(tmp_path / "npz", kind="npz", seed=0)

    # docs/data-layer.md records this boundary: upstream io.load_run sees a
    # run directory, pickle.loads sampler_state.pkl, and therefore rejects the
    # ZIP-shaped NPZ fixture.  The GUI loader falls back to its magic-aware
    # numpy-only path and succeeds on the same directory.
    with pytest.raises(Exception) as error:
        upstream_load_run(str(run), stubs=True)
    assert "persistent id" in str(error.value).lower() or "pickle" in str(error.value).lower()

    gui_result = load_result(run)

    assert isinstance(gui_result, (LightRunResult,))
    assert gui_result.kind == "npz"
    assert gui_result.samples.shape == (32, 5)
    assert gui_result.log_densities.shape == (32,)
    assert gui_result.best_index == 0
