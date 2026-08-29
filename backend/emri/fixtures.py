"""Deterministic, heavy-stack-free synthetic run-directory builders.

Fixtures use the same sidecar names and manifest keys as upstream, but their
sampler is a plain duck-typed object.  No ``parismc`` or waveform package is
imported, which keeps data-layer tests runnable on a small Python environment.
"""
from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np

from .summary import MANIFEST_NAME, STATE_NAME


class UnitCubeTransform:
    """Pickleable affine unit-cube -> search-coordinate transform."""

    def __init__(self, lo: Any, hi: Any) -> None:
        self.lo = np.asarray(lo, dtype=float)
        self.hi = np.asarray(hi, dtype=float)

    def __call__(self, points: Any) -> np.ndarray:
        unit = np.asarray(points, dtype=float)
        return self.lo + (self.hi - self.lo) * unit


class FakeSampler:
    """Small PARIS-shaped sampler used only by fixture runs."""

    def __init__(self, samples: Any, log_densities: Any, lo: Any, hi: Any) -> None:
        self._samples = np.asarray(samples, dtype=float)
        self._log_densities = np.asarray(log_densities, dtype=float)
        self._weights = np.ones(len(self._samples), dtype=float)
        self.prior_transform = UnitCubeTransform(lo, hi)
        points_u = (self._samples - self.prior_transform.lo) / (
            self.prior_transform.hi - self.prior_transform.lo
        )
        n_processes = min(4, max(1, len(self._samples)))
        self.n_proc = n_processes
        point_parts = np.array_split(points_u, n_processes)
        value_parts = np.array_split(self._log_densities, n_processes)
        self.element_num_list = [len(part) for part in point_parts]
        self.searched_points_list = [np.asarray(part, dtype=float) for part in point_parts]
        self.searched_log_densities_list = [
            np.asarray(part, dtype=float) for part in value_parts
        ]

    def get_samples_with_weights(self, flatten: bool = True):
        if not flatten:
            return self._samples.copy(), self._weights.copy()
        return self._samples.copy(), self._weights.copy()

    def apply_prior_transform(self, points: Any, prior_transform: Any) -> np.ndarray:
        return np.asarray(prior_transform(points), dtype=float)


# Public alias makes the fixture's duck-typed intent obvious to test authors.
DuckSampler = FakeSampler


def _source() -> dict[str, float]:
    return {
        "m1": 3.0e5,
        "m2": 10.0,
        "a": 0.3,
        "p0": 12.0,
        "e0": 0.2,
        "xI0": 0.5,
        "dist": 1.0,
        "qS": 1.2,
        "phiS": 2.1,
        "qK": 0.8,
        "phiK": 4.0,
        "Phi_phi0": 0.0,
        "Phi_theta0": 0.0,
        "Phi_r0": 0.0,
    }


def _free_space() -> list[dict[str, Any]]:
    return [
        {"name": "m1", "transform": "log10", "lo": 5.2, "hi": 6.0},
        {"name": "m2", "transform": "log10", "lo": 0.5, "hi": 1.5},
        {"name": "a", "transform": "identity", "lo": 0.0, "hi": 0.9},
        {"name": "p0", "transform": "identity", "lo": 8.0, "hi": 16.0},
        {"name": "e0", "transform": "identity", "lo": 0.0, "hi": 0.5},
    ]


def _truth_search(source: Mapping[str, float], free: list[Mapping[str, Any]]) -> np.ndarray:
    result = []
    for item in free:
        value = float(source[str(item["name"])])
        transform = str(item["transform"])
        if transform == "log10":
            value = float(np.log10(value))
        elif transform == "cos":
            value = float(np.cos(value))
        result.append(value)
    return np.asarray(result, dtype=float)


def _manifest(path: Path, seed: int, seeding: Optional[Mapping[str, Any]] = None) -> dict:
    source = _source()
    free = _free_space()
    fixed = {key: value for key, value in source.items() if key not in {item["name"] for item in free}}
    return {
        "emrisearch_version": "0.1.0",
        "source": source,
        "obs": {
            "T": 0.5,
            "dt": 5.0,
            "tdi_gen": 1,
            "use_gpu": False,
            "pad_output": False,
        },
        "noise": {"add": True, "seed": int(seed)},
        "modes": {
            "ell": 2,
            "n_vals": list(range(-1, 6)),
            "M_mode": None,
            "N_traj": 5000,
            "mode_select": None,
        },
        "statistic": {"kind": "pure"},
        "space": {"free": free, "truth": source, "fixed": fixed},
        "sampler": {
            "n_seed": 10,
            "num_iterations": 20,
            "print_iter": 10,
            "save_every": 10,
            "init_cov": 0.1,
            "merge_confidence": 0.9,
            "alpha": 1000,
            "trail_size": 1000,
            "boundary_limiting": True,
            "use_beta": True,
            "integral_num": 100000,
            "gamma": 500,
            "exclude_scale_z": "inf",
            "use_pool": False,
            "keep_dead_processes": True,
            "seed": int(seed),
        },
        "seeding": dict(
            seeding or {"kind": "internal_lhs", "n": 32, "batch_size": 8}
        ),
        # Fixtures write a relative out so same-seed manifests are byte-identical
        # across directories (upstream's absolute `out`, run.py:300, depends on
        # where the run lives). Tests that inspect `out` use the run path.
        "out": ".",
    }


def _arrays(seed: int, count: int = 32) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(int(seed))
    source = _source()
    free = _free_space()
    truth = _truth_search(source, free)
    lo = np.asarray([float(item["lo"]) for item in free], dtype=float)
    hi = np.asarray([float(item["hi"]) for item in free], dtype=float)
    scale = np.asarray([0.06, 0.06, 0.08, 0.7, 0.05], dtype=float)
    samples = truth + rng.normal(0.0, scale, size=(count, len(free)))
    samples = np.clip(samples, lo, hi)
    samples[0] = truth
    log_densities = -np.sum(((samples - truth) / scale) ** 2, axis=1)
    log_densities[0] = 0.0
    return samples, log_densities, lo, hi


def _write_state(
    directory: Path,
    kind: str,
    samples: np.ndarray,
    log_densities: np.ndarray,
    lo: np.ndarray,
    hi: np.ndarray,
) -> None:
    state = directory / STATE_NAME
    if kind == "parismc_sampler":
        with state.open("wb") as handle:
            pickle.dump(FakeSampler(samples, log_densities, lo, hi), handle, protocol=4)
    elif kind == "lhs_tuple":
        with state.open("wb") as handle:
            pickle.dump((samples, log_densities), handle, protocol=4)
    elif kind == "lhs_dict":
        with state.open("wb") as handle:
            pickle.dump(
                {"samples": samples, "log_densities": log_densities},
                handle,
                protocol=4,
            )
    elif kind == "npz":
        # Keep the upstream STATE_NAME so scan_run_root discovers it.  The
        # loader recognizes the ZIP magic and applies the upstream npz shape.
        with state.open("wb") as handle:
            np.savez(handle, samples=samples, log_densities=log_densities)
    else:
        raise ValueError(
            "kind must be one of parismc_sampler, lhs_tuple, lhs_dict, npz"
        )


def make_manifest_run(
    directory: os.PathLike | str,
    kind: str = "parismc_sampler",
    seed: int = 0,
) -> Path:
    """Create one deterministic manifest + state fixture and return its path."""
    if kind not in {"parismc_sampler", "lhs_tuple", "lhs_dict", "npz"}:
        raise ValueError(
            "kind must be one of parismc_sampler, lhs_tuple, lhs_dict, npz"
        )
    path = Path(directory).expanduser().resolve(strict=False)
    path.mkdir(parents=True, exist_ok=True)
    samples, log_densities, lo, hi = _arrays(seed)
    manifest = _manifest(path, seed)
    with (path / MANIFEST_NAME).open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    _write_state(path, kind, samples, log_densities, lo, hi)
    return path


def make_legacy_run(
    directory: os.PathLike | str,
    kind: str = "lhs_tuple",
    seed: int = 0,
) -> Path:
    """Create a state-only legacy fixture (there is deliberately no manifest)."""
    path = Path(directory).expanduser().resolve(strict=False)
    path.mkdir(parents=True, exist_ok=True)
    samples, log_densities, lo, hi = _arrays(seed)
    _write_state(path, kind, samples, log_densities, lo, hi)
    try:
        (path / MANIFEST_NAME).unlink()
    except FileNotFoundError:
        pass
    return path


# Concise alias for callers that use the domain term rather than the full name.
make_legacy = make_legacy_run


def make_run_chain(
    root: os.PathLike | str,
    n_stages: int,
) -> list[Path]:
    """Create a deterministic ``stage_00 -> ... -> stage_N`` lineage."""
    if isinstance(n_stages, bool) or int(n_stages) < 0:
        raise ValueError("n_stages must be a non-negative integer")
    root_path = Path(root).expanduser().resolve(strict=False)
    root_path.mkdir(parents=True, exist_ok=True)
    stages: list[Path] = []
    for index in range(int(n_stages)):
        stage = root_path / f"stage_{index:02d}"
        make_manifest_run(stage, kind="parismc_sampler", seed=index)
        if index:
            manifest_path = stage / MANIFEST_NAME
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            manifest["seeding"] = {
                "kind": "from_run",
                "path": f"../{stages[-1].name}",
                "n_sigma": 3.0,
            }
            with manifest_path.open("w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2, sort_keys=True)
                handle.write("\n")
        stages.append(stage)
    return stages


__all__ = [
    "UnitCubeTransform", "FakeSampler", "DuckSampler", "make_manifest_run",
    "make_legacy_run", "make_legacy", "make_run_chain",
]
