"""Deterministic, lightweight fixture strategy tests."""

import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from backend.emri import load_result, make_manifest_run
from backend.emri.fixtures import DuckSampler, FakeSampler, UnitCubeTransform


STORAGE_KINDS = ("parismc_sampler", "lhs_tuple", "lhs_dict", "npz")


def _manifest(path):
    return json.loads((path / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind", STORAGE_KINDS)
def test_each_manifest_fixture_writes_both_expected_files(tmp_path, kind):
    run = make_manifest_run(tmp_path / kind, kind=kind, seed=7)

    assert run.is_dir()
    assert (run / "manifest.json").is_file()
    assert (run / "sampler_state.pkl").is_file()


@pytest.mark.xfail(
    reason=(
        "manifest out is currently an absolute fixture-directory path, so the "
        "same-seed manifests are not byte-identical across directories"
    ),
    strict=False,
)
def test_same_seed_manifests_are_byte_identical_across_directories(tmp_path):
    first = make_manifest_run(tmp_path / "first", kind="lhs_tuple", seed=11)
    second = make_manifest_run(tmp_path / "second", kind="lhs_tuple", seed=11)

    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()


@pytest.mark.parametrize("kind", STORAGE_KINDS)
def test_same_seed_loaded_arrays_are_identical_and_different_seed_changes_data(tmp_path, kind):
    first = make_manifest_run(tmp_path / "first", kind=kind, seed=11)
    second = make_manifest_run(tmp_path / "second", kind=kind, seed=11)
    changed = make_manifest_run(tmp_path / "changed", kind=kind, seed=12)

    first_result = load_result(first)
    second_result = load_result(second)
    changed_result = load_result(changed)
    assert first_result.kind == second_result.kind == kind
    np.testing.assert_array_equal(first_result.samples, second_result.samples)
    np.testing.assert_array_equal(first_result.log_densities, second_result.log_densities)
    assert not np.array_equal(first_result.samples, changed_result.samples)
    assert not np.array_equal(first_result.log_densities, changed_result.log_densities)

    first_manifest = _manifest(first)
    second_manifest = _manifest(second)
    changed_manifest = _manifest(changed)
    # The varying output path is the only known directory-local field; all
    # random/configuration fields are deterministic for a fixed seed.
    first_manifest["out"] = second_manifest["out"] = changed_manifest["out"] = "<run>"
    assert first_manifest == second_manifest
    assert first_manifest != changed_manifest


def test_fake_sampler_exposes_the_full_duck_typed_surface(tmp_path):
    run = make_manifest_run(tmp_path / "paris", kind="parismc_sampler", seed=0)
    with (run / "sampler_state.pkl").open("rb") as handle:
        sampler = pickle.load(handle)

    assert isinstance(sampler, FakeSampler)
    assert DuckSampler is FakeSampler
    assert callable(sampler.get_samples_with_weights)
    assert hasattr(sampler, "n_proc")
    assert hasattr(sampler, "element_num_list")
    assert hasattr(sampler, "searched_points_list")
    assert hasattr(sampler, "searched_log_densities_list")
    assert hasattr(sampler, "prior_transform")
    assert callable(sampler.apply_prior_transform)
    assert sampler.n_proc == 4
    assert len(sampler.element_num_list) == sampler.n_proc
    assert len(sampler.searched_points_list) == sampler.n_proc
    assert len(sampler.searched_log_densities_list) == sampler.n_proc
    assert sum(sampler.element_num_list) == 32
    assert sampler.get_samples_with_weights()[0].shape == (32, 5)
    assert sampler.get_samples_with_weights()[1].shape == (32,)

    unit = np.zeros((1, 5), dtype=float)
    transformed = sampler.apply_prior_transform(unit, sampler.prior_transform)
    np.testing.assert_allclose(transformed, sampler.prior_transform.lo[None, :])
    assert isinstance(UnitCubeTransform(sampler.prior_transform.lo, sampler.prior_transform.hi), UnitCubeTransform)


def test_fixture_imports_do_not_pull_heavy_stack_into_a_fresh_interpreter(tmp_path):
    """Use a child process so other tests cannot contaminate sys.modules."""
    repo_root = Path(__file__).resolve().parents[2]
    code = """
import json
import sys
import backend.emri
import backend.emri.fixtures
roots = ("parismc", "emrisearch", "matplotlib", "corner")
heavy = sorted(
    name for name in sys.modules
    if any(name == root or name.startswith(root + ".") for root in roots)
)
print(json.dumps(heavy))
assert not heavy, heavy
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(repo_root), env.get("PYTHONPATH", "")) if item
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout.strip()) == []
