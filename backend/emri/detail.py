"""Full run loading and GUI-side diagnostics.

The preferred loader is ``emrisearch.io.load_run`` when the optional upstream
package is importable.  A small numpy-only loader is kept here as a deliberate
fallback so the explorer and its fixtures work on a machine without PARIS,
FastEMRIWaveforms, or the other heavy runtime dependencies.
"""
from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

import numpy as np

from .summary import MANIFEST_NAME, STATE_NAME, summarize_run
from .types import (
    BestPerProcessTable,
    BestPoint,
    BestPointDimension,
    Diagnostics,
    ManifestDetails,
    NSigmaRow,
    NSigmaTable,
    ProcessBest,
    RunDetail,
    RunSummary,
    SampleCounts,
    SearchDimension,
    SearchSpaceTable,
    UNSET,
)

_PREFIX = {"identity": "", "log10": "log10_", "cos": "cos_"}
_TRANSFORM_ALIASES = {"linear": "identity"}


def _normal_transform(value: Any) -> str:
    text = str(value) if value not in (None, "") else UNSET
    return _TRANSFORM_ALIASES.get(text, text)


def _base_name(name: Any, transform: str) -> str:
    text = str(name) if name not in (None, "") else UNSET
    prefix = _PREFIX.get(transform, "")
    if prefix and text.startswith(prefix):
        return text[len(prefix):]
    # Prototype exports used ``log10_m1``/``cos_qS`` as the name itself; accept
    # those while retaining canonical upstream names in new fixtures.
    for known in ("log10_", "cos_"):
        if text.startswith(known):
            return text[len(known):]
    return text


def _search_name(name: Any, transform: str) -> str:
    text = str(name) if name not in (None, "") else UNSET
    if text.startswith(("log10_", "cos_")):
        return text
    return _PREFIX.get(transform, "") + text


def _number(value: Any, finite: bool = False) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if finite and not np.isfinite(number):
        return None
    return number


def _display(value: Any) -> Any:
    """Replace nulls recursively for display, without changing raw JSON."""
    if value is None:
        return UNSET
    if isinstance(value, Mapping):
        return {str(key): _display(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_display(item) for item in value)
    if isinstance(value, list):
        return [_display(item) for item in value]
    return value


@dataclass(frozen=True)
class _Param:
    name: str
    transform: str
    lo: Any
    hi: Any
    search_coord: str

    def to_physical(self, value: float) -> float:
        if self.transform == "log10":
            return float(np.power(10.0, value))
        if self.transform == "cos":
            return float(np.arccos(value))
        return float(value)

    def to_search(self, value: float) -> float:
        if self.transform == "log10":
            return float(np.log10(value))
        if self.transform == "cos":
            return float(np.cos(value))
        return float(value)


class LightParamSpace:
    """Small ``ParamSpace``-compatible view reconstructed from a manifest."""

    def __init__(
        self,
        params: Sequence[_Param] = (),
        truth: Optional[Mapping[str, Any]] = None,
        fixed: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.free = tuple(params)
        self.truth = dict(truth or {})
        self.fixed = dict(fixed or {})

    @property
    def ndim(self) -> int:
        return len(self.free)

    @property
    def names(self) -> Tuple[str, ...]:
        return tuple(param.search_coord for param in self.free)

    @property
    def labels(self) -> Tuple[str, ...]:
        return self.names

    @property
    def lo(self) -> np.ndarray:
        return np.asarray([param.lo for param in self.free], dtype=float)

    @property
    def hi(self) -> np.ndarray:
        return np.asarray([param.hi for param in self.free], dtype=float)

    @property
    def box(self) -> Tuple[Tuple[float, float], ...]:
        return tuple((param.lo, param.hi) for param in self.free)

    def _truth_value(self, param: _Param) -> Optional[float]:
        for key in (param.name, param.search_coord):
            if key in self.truth:
                return _number(self.truth[key])
        return None

    @property
    def truth_search(self) -> np.ndarray:
        values = []
        for param in self.free:
            if param.name not in self.truth and param.search_coord in self.truth:
                value = _number(self.truth[param.search_coord])
                values.append(np.nan if value is None else value)
                continue
            physical = self._truth_value(param)
            if physical is None:
                values.append(np.nan)
            else:
                try:
                    values.append(param.to_search(physical))
                except (TypeError, ValueError, FloatingPointError):
                    values.append(np.nan)
        return np.asarray(values, dtype=float)

    def prior_transform(self, unit_cube: Any) -> np.ndarray:
        unit = np.asarray(unit_cube, dtype=float)
        return self.lo + (self.hi - self.lo) * unit

    def inverse_prior_transform(self, search: Any) -> np.ndarray:
        value = np.asarray(search, dtype=float)
        return (value - self.lo) / (self.hi - self.lo)

    def to_physical(self, search: Sequence[float]) -> Mapping[str, float]:
        values = dict(self.truth)
        values.update(self.fixed)
        vector = np.asarray(search, dtype=float).reshape(-1)
        if vector.size != self.ndim:
            raise ValueError(f"expected {self.ndim} coordinates, got {vector.size}")
        for param, value in zip(self.free, vector):
            values[param.name] = param.to_physical(float(value))
        return values

    def to_search(self, physical: Mapping[str, Any]) -> np.ndarray:
        values = []
        for param in self.free:
            if isinstance(physical, Mapping):
                value = physical.get(param.name, physical.get(param.search_coord, np.nan))
            else:
                value = getattr(physical, param.name, np.nan)
            values.append(param.to_search(float(value)))
        return np.asarray(values, dtype=float)

    def contains(self, search: Any) -> np.ndarray:
        value = np.asarray(search, dtype=float)
        return np.all((value >= self.lo) & (value <= self.hi), axis=-1)

    def __repr__(self) -> str:
        return f"LightParamSpace(ndim={self.ndim}, names={self.names})"


def _space_from_manifest(manifest: Mapping[str, Any]) -> LightParamSpace:
    raw_space = manifest.get("space")
    raw_space = raw_space if isinstance(raw_space, Mapping) else {}
    params: list[_Param] = []
    free = raw_space.get("free", [])
    if isinstance(free, (list, tuple)):
        for entry in free:
            if not isinstance(entry, Mapping):
                continue
            transform = _normal_transform(entry.get("transform", "identity"))
            name = _base_name(entry.get("name", UNSET), transform)
            search_coord = _search_name(entry.get("name", UNSET), transform)
            lo = entry.get("lo", UNSET)
            hi = entry.get("hi", UNSET)
            params.append(
                _Param(
                    name=name,
                    transform=transform,
                    lo=UNSET if lo is None else lo,
                    hi=UNSET if hi is None else hi,
                    search_coord=search_coord,
                )
            )
    truth = raw_space.get("truth")
    if not isinstance(truth, Mapping):
        truth = manifest.get("source") if isinstance(manifest.get("source"), Mapping) else {}
    fixed = raw_space.get("fixed")
    if not isinstance(fixed, Mapping):
        fixed = {}
    return LightParamSpace(params, truth=truth, fixed=fixed)


def _space_table(space: LightParamSpace, manifest: Mapping[str, Any]) -> SearchSpaceTable:
    dimensions = tuple(
        SearchDimension(
            name=param.name,
            transform=param.transform,
            lo=param.lo,
            hi=param.hi,
            search_coord=param.search_coord,
        )
        for param in space.free
    )
    return SearchSpaceTable(
        dimensions=dimensions,
        fixed=_display(space.fixed),
        truth=_display(space.truth),
    )


def _read_manifest(path: Path) -> Optional[dict]:
    run_path = path if path.is_dir() else path.parent
    manifest_path = run_path / MANIFEST_NAME
    if not manifest_path.exists():
        return None
    with manifest_path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise ValueError(f"manifest {manifest_path} must contain a JSON object")
    return dict(value)


class LightRunResult:
    """Numpy-only equivalent of the useful part of upstream ``RunResult``."""

    def __init__(
        self,
        samples: Any,
        log_densities: Any,
        weights: Any = None,
        manifest: Optional[Mapping[str, Any]] = None,
        path: Optional[os.PathLike | str] = None,
        kind: Optional[str] = None,
        sampler: Any = None,
        ndim: Optional[int] = None,
    ) -> None:
        array = np.asarray(samples, dtype=float)
        if array.ndim == 0:
            array = np.atleast_2d(array)
        elif array.ndim == 1:
            if array.size == 0 and ndim is not None:
                array = np.empty((0, int(ndim)), dtype=float)
            else:
                array = np.atleast_2d(array)
        if array.ndim != 2:
            raise ValueError(f"samples must be 2-D, got shape {array.shape}")
        values = np.asarray(log_densities, dtype=float).reshape(-1)
        if len(values) != len(array):
            raise ValueError(
                f"samples ({len(array)}) and log_densities ({len(values)}) disagree"
            )
        self.samples = array
        self.log_densities = values
        self.weights = None if weights is None else np.asarray(weights, dtype=float).reshape(-1)
        if self.weights is not None and len(self.weights) != len(array):
            raise ValueError("weights and samples disagree in length")
        self.manifest = None if manifest is None else dict(manifest)
        self.path = None if path is None else str(path)
        self.kind = kind
        self.sampler = sampler

    @property
    def ndim(self) -> int:
        return int(self.samples.shape[1])

    @property
    def best_index(self) -> int:
        return int(np.nanargmax(self.log_densities))

    @property
    def best(self) -> np.ndarray:
        return self.samples[self.best_index]

    def finite(self) -> "LightRunResult":
        mask = np.isfinite(self.log_densities)
        return LightRunResult(
            self.samples[mask],
            self.log_densities[mask],
            None if self.weights is None else self.weights[mask],
            self.manifest,
            self.path,
            self.kind,
            self.sampler,
        )

    def top(self, n: int) -> "LightRunResult":
        indices = np.argsort(self.log_densities)[::-1][: int(n)]
        return LightRunResult(
            self.samples[indices],
            self.log_densities[indices],
            None if self.weights is None else self.weights[indices],
            self.manifest,
            self.path,
            self.kind,
            self.sampler,
        )

    def param_space(self) -> LightParamSpace:
        if not isinstance(self.manifest, Mapping) or "space" not in self.manifest:
            raise ValueError("no parameter space recorded in this result")
        return _space_from_manifest(self.manifest)

    def posterior_covariance(self) -> np.ndarray:
        if len(self.samples) < 2:
            raise ValueError("at least two samples are required for covariance")
        weights = np.ones(len(self.samples), dtype=float) if self.weights is None else self.weights.copy()
        if not np.all(np.isfinite(weights)) or np.sum(weights) <= 0:
            raise ValueError("weights are not finite and positive")
        weights /= np.sum(weights)
        denominator = 1.0 - np.sum(weights**2)
        if denominator <= 0:
            raise ValueError("effective sample count is one")
        mean = np.average(self.samples, axis=0, weights=weights)
        delta = self.samples - mean
        return (delta * weights[:, None]).T @ delta / denominator

    def __repr__(self) -> str:
        return f"LightRunResult(n={len(self.samples)}, ndim={self.ndim}, kind={self.kind!r})"


def _npz_result(path: Path, manifest: Optional[Mapping[str, Any]] = None) -> LightRunResult:
    with np.load(path, allow_pickle=False) as data:
        keys = set(data.files)
        embedded_manifest = manifest
        if embedded_manifest is None and "manifest" in keys:
            try:
                raw_manifest = data["manifest"]
                if isinstance(raw_manifest, np.ndarray) and raw_manifest.ndim == 0:
                    raw_manifest = raw_manifest.item()
                if isinstance(raw_manifest, bytes):
                    raw_manifest = raw_manifest.decode("utf-8")
                parsed_manifest = json.loads(str(raw_manifest))
                if isinstance(parsed_manifest, Mapping):
                    embedded_manifest = parsed_manifest
            except (TypeError, ValueError, json.JSONDecodeError):
                embedded_manifest = manifest
        for points_key, values_key in (
            ("samples", "log_densities"),
            ("lhs_phys", "log_densities"),
            ("phys_pts", "det_snr"),
        ):
            if points_key in keys and values_key in keys:
                return LightRunResult(
                    data[points_key],
                    data[values_key],
                    manifest=embedded_manifest,
                    path=path,
                    kind="npz",
                )
        if "x_map" in keys:
            values = data["lnL_map"] if "lnL_map" in keys else np.array([np.nan])
            return LightRunResult(
                np.atleast_2d(data["x_map"]),
                values,
                manifest=embedded_manifest,
                path=path,
                kind="npz_map",
            )
    raise ValueError(f"{path} has no supported NPZ result shape")


def _from_sampler(sampler: Any, manifest: Optional[Mapping[str, Any]], path: Path) -> LightRunResult:
    samples = weights = None
    getter = getattr(sampler, "get_samples_with_weights", None)
    if callable(getter):
        try:
            samples, weights = getter(flatten=True)
        except Exception:
            samples = weights = None

    searched: list[np.ndarray] = []
    logdensities: list[np.ndarray] = []
    try:
        n_proc = int(sampler.n_proc)
        for index in range(n_proc):
            count = int(sampler.element_num_list[index])
            searched.append(np.asarray(sampler.searched_points_list[index][:count], dtype=float))
            logdensities.append(
                np.asarray(sampler.searched_log_densities_list[index][:count], dtype=float)
            )
    except Exception:
        searched = []
        logdensities = []

    if searched:
        points_u = np.concatenate(searched, axis=0)
        values = np.concatenate(logdensities, axis=0)
        try:
            points = np.asarray(
                sampler.apply_prior_transform(points_u, sampler.prior_transform), dtype=float
            )
        except Exception:
            points = points_u
        return LightRunResult(
            points,
            values,
            manifest=manifest,
            path=path,
            kind="parismc_sampler",
            sampler=sampler,
        )
    if samples is None:
        raise ValueError(f"could not extract samples from sampler in {path}")
    return LightRunResult(
        samples,
        np.full(len(np.asarray(samples)), np.nan),
        weights,
        manifest,
        path,
        "parismc_sampler",
        sampler,
    )


def _load_light_result(path: os.PathLike | str) -> LightRunResult:
    original = Path(path).expanduser()
    manifest = _read_manifest(original)
    if original.is_dir():
        state_path = original / STATE_NAME
        if not state_path.exists():
            npz_candidates = sorted(original.glob("*.npz"))
            if npz_candidates:
                return _npz_result(npz_candidates[0], manifest)
            raise FileNotFoundError(f"{original} contains no {STATE_NAME}")
    else:
        state_path = original

    if state_path.suffix == ".npz":
        return _npz_result(state_path, manifest)
    try:
        raw = state_path.read_bytes()
    except OSError:
        raise
    if raw[:4] == b"PK\x03\x04":
        return _npz_result(state_path, manifest)
    try:
        obj = pickle.loads(raw)
    except Exception as exc:
        raise ValueError(f"could not unpickle result {state_path}: {exc}") from exc

    if isinstance(obj, tuple) and len(obj) == 2:
        return LightRunResult(
            obj[0], obj[1], manifest=manifest, path=state_path, kind="lhs_tuple"
        )
    if isinstance(obj, Mapping):
        for points_key, values_key in (
            ("lhs_phys", "log_densities"),
            ("phys_pts", "det_snr"),
            ("samples", "log_densities"),
        ):
            if points_key in obj and values_key in obj:
                return LightRunResult(
                    obj[points_key],
                    obj[values_key],
                    manifest=obj if manifest is None else manifest,
                    path=state_path,
                    kind="lhs_dict",
                )
        raise ValueError(f"{state_path} has no supported legacy dict key pair")
    if hasattr(obj, "get_samples_with_weights"):
        return _from_sampler(obj, manifest, state_path)
    raise ValueError(f"{state_path} holds an unsupported object {type(obj).__name__}")


def _try_upstream(path: os.PathLike | str) -> Any:
    """Load through upstream when present; return ``None`` on optional failure."""
    try:
        from emrisearch.io import load_run as upstream_load_run
    except ImportError:
        return None
    try:
        return upstream_load_run(str(path), stubs=True)
    except Exception:
        # The fallback is needed for the deliberately NPZ-shaped fixture state
        # and for environments with an upstream package but no its pickle deps.
        return None


def load_result(path: os.PathLike | str) -> Any:
    """Load a result with the optional upstream loader and local fallback."""
    upstream = _try_upstream(path)
    return upstream if upstream is not None else _load_light_result(path)


def _best_vector(result: Any) -> Tuple[Optional[int], Optional[np.ndarray], Optional[float]]:
    try:
        index = int(result.best_index)
        vector = np.asarray(result.best, dtype=float).reshape(-1)
        values = np.asarray(result.log_densities, dtype=float).reshape(-1)
        value = _number(values[index], finite=False)
        return index, vector, value
    except (AttributeError, IndexError, TypeError, ValueError):
        return None, None, None


def _physical_vector(space: Any, search: Sequence[float]) -> Tuple[Any, ...]:
    values = np.asarray(search, dtype=float).reshape(-1)
    if isinstance(space, LightParamSpace):
        return tuple(
            param.to_physical(float(value))
            for param, value in zip(space.free, values)
        )
    free = getattr(space, "free", ())
    result = []
    for param, value in zip(free, values):
        try:
            result.append(param.to_physical(float(value)))
        except Exception:
            result.append(UNSET)
    return tuple(result)


def _best_point(result: Any, space: LightParamSpace) -> BestPoint:
    _index, vector, log_density = _best_vector(result)
    if vector is None:
        return BestPoint(log_density=None)
    dimensions: list[BestPointDimension] = []
    physical = _physical_vector(space, vector)
    if space.free:
        for index, param in enumerate(space.free):
            value = float(vector[index]) if index < len(vector) else UNSET
            physical_value = physical[index] if index < len(physical) else UNSET
            dimensions.append(
                BestPointDimension(
                    name=param.name,
                    transform=param.transform,
                    search=value,
                    physical=physical_value,
                )
            )
    else:
        for index, value in enumerate(vector):
            dimensions.append(
                BestPointDimension(
                    name=f"dim_{index}",
                    transform="identity",
                    search=float(value),
                    physical=float(value),
                )
            )
    return BestPoint(
        log_density=log_density,
        dimensions=tuple(dimensions),
        search_coordinates=tuple(float(value) for value in vector),
        physical_coordinates=tuple(physical) if physical else tuple(float(value) for value in vector),
    )


def n_sigma_to_contain(
    result: Any,
    space: Optional[Any] = None,
    truth: Optional[Sequence[float]] = None,
    best: Optional[Sequence[float]] = None,
) -> NSigmaTable:
    """Compute ``|best_i - truth_i| / sigma_i`` per searched dimension.

    ``sigma`` is the square root of the posterior-covariance diagonal in search
    coordinates.  Missing covariance, truth, or a non-positive sigma produces
    the display sentinel ``"unset"``.  This is GUI policy rather than an
    upstream ``RunResult`` method.
    """
    if space is None:
        try:
            space = result.param_space()
        except Exception:
            space = LightParamSpace()
    dimensions = tuple(getattr(space, "free", ()))
    names = []
    if isinstance(space, LightParamSpace):
        names = [param.name for param in space.free]
    else:
        names = [getattr(param, "name", f"dim_{i}") for i, param in enumerate(dimensions)]
    if best is None:
        _index, best_vector, _value = _best_vector(result)
    elif isinstance(best, BestPoint):
        best_vector = np.asarray(best.search_coordinates, dtype=float)
    else:
        best_vector = np.asarray(best, dtype=float).reshape(-1)
    if best_vector is None:
        best_vector = np.asarray([], dtype=float)
    if truth is None:
        try:
            truth_vector = np.asarray(space.truth_search, dtype=float).reshape(-1)
        except Exception:
            truth_vector = np.asarray([], dtype=float)
    else:
        truth_vector = np.asarray(truth, dtype=float).reshape(-1)

    sigma = None
    try:
        finite_result = result.finite()
        covariance = np.asarray(finite_result.posterior_covariance(), dtype=float)
        diagonal = np.diag(covariance)
        sigma = np.sqrt(np.clip(diagonal, 0.0, None))
    except Exception:
        sigma = None

    ndim = max(len(names), len(best_vector), len(truth_vector))
    rows = []
    for index in range(ndim):
        name = names[index] if index < len(names) else f"dim_{index}"
        best_value = (
            float(best_vector[index])
            if index < len(best_vector) and np.isfinite(best_vector[index])
            else UNSET
        )
        truth_value = (
            float(truth_vector[index])
            if index < len(truth_vector) and np.isfinite(truth_vector[index])
            else UNSET
        )
        sigma_value = (
            float(sigma[index])
            if sigma is not None and index < len(sigma) and np.isfinite(sigma[index])
            else UNSET
        )
        if (
            best_value == UNSET
            or truth_value == UNSET
            or sigma_value == UNSET
            or sigma_value <= 0
        ):
            value: Any = UNSET
        else:
            value = max(0.0, abs(best_value - truth_value) / sigma_value)
        rows.append(NSigmaRow(name, best_value, truth_value, sigma_value, value))
    available = bool(
        sigma is not None
        and np.any(np.isfinite(sigma) & (np.asarray(sigma) > 0))
    )
    return NSigmaTable(rows=tuple(rows), available=available)


def _mapped_process_point(sampler: Any, point: Any) -> np.ndarray:
    raw = np.asarray(point, dtype=float).reshape(1, -1)
    try:
        mapped = sampler.apply_prior_transform(raw, sampler.prior_transform)
        return np.asarray(mapped, dtype=float).reshape(-1)
    except Exception:
        return raw.reshape(-1)


def best_per_process(sampler_or_result: Any, space: Optional[Any] = None) -> BestPerProcessTable:
    """Read process-local bests from PARIS state when all state fields exist.

    The process lists contain unit-cube points upstream, so each selected point
    is passed through ``apply_prior_transform(points, prior_transform)`` before
    it is exposed as a search-coordinate row.  The prototype's read is
    ``merged`` when the log-density spread is below 5.0; otherwise it is
    ``unmerged``.  Non-PARIS result shapes return an unavailable table.
    """
    sampler = getattr(sampler_or_result, "sampler", None)
    if sampler is None:
        sampler = sampler_or_result
    required = (
        "n_proc",
        "element_num_list",
        "searched_points_list",
        "searched_log_densities_list",
        "prior_transform",
        "apply_prior_transform",
    )
    if any(not hasattr(sampler, name) for name in required):
        return BestPerProcessTable()
    rows: list[ProcessBest] = []
    numeric_values: list[float] = []
    try:
        count_processes = int(sampler.n_proc)
        for process in range(count_processes):
            count = int(sampler.element_num_list[process])
            points = np.asarray(sampler.searched_points_list[process][:count], dtype=float)
            values = np.asarray(
                sampler.searched_log_densities_list[process][:count], dtype=float
            ).reshape(-1)
            usable = min(len(points), len(values))
            points, values = points[:usable], values[:usable]
            if usable == 0 or not np.any(np.isfinite(values)):
                rows.append(ProcessBest(process=process))
                continue
            index = int(np.nanargmax(values))
            log_density = float(values[index])
            search = _mapped_process_point(sampler, points[index])
            physical = _physical_vector(space, search) if space is not None else ()
            rows.append(
                ProcessBest(
                    process=process,
                    log_density=log_density,
                    search_coordinates=tuple(float(v) for v in search),
                    physical_coordinates=tuple(physical),
                )
            )
            numeric_values.append(log_density)
    except Exception:
        return BestPerProcessTable()
    if not rows:
        return BestPerProcessTable(rows=(), available=True)
    spread: Any = UNSET
    merged: Any = UNSET
    if numeric_values:
        spread = float(max(numeric_values) - min(numeric_values))
        merged = bool(spread < 5.0)
    return BestPerProcessTable(
        rows=tuple(rows), spread=spread, merged=merged, available=True
    )


def _manifest_groups(manifest: Mapping[str, Any], space: LightParamSpace) -> ManifestDetails:
    def group(name: str) -> Mapping[str, Any]:
        value = manifest.get(name)
        return _display(value) if isinstance(value, Mapping) else {}

    return ManifestDetails(
        emrisearch_version=_display(manifest.get("emrisearch_version", UNSET)),
        source=group("source"),
        obs=group("obs"),
        noise=group("noise"),
        modes=group("modes"),
        statistic=group("statistic"),
        space=_space_table(space, manifest),
        sampler=group("sampler"),
        seeding=group("seeding"),
        out=_display(manifest.get("out", UNSET)),
        raw=dict(manifest),
    )


def _fallback_summary(path: Path, manifest: Mapping[str, Any], result: Any) -> RunSummary:
    seeding = manifest.get("seeding") if isinstance(manifest.get("seeding"), Mapping) else {}
    statistic = manifest.get("statistic") if isinstance(manifest.get("statistic"), Mapping) else {}
    try:
        ndim = int(result.ndim)
    except Exception:
        ndim = None
    _index, _vector, best = _best_vector(result)
    return RunSummary(
        id=path.name,
        path=str(path.resolve(strict=False)),
        kind=str(seeding.get("kind", UNSET)),
        statistic=str(statistic.get("kind", UNSET)),
        ndim=ndim,
        best_log_density=best if best is not None and np.isfinite(best) else None,
        from_run=seeding.get("path") if seeding.get("kind") == "from_run" else None,
        out=str(manifest.get("out", path.resolve(strict=False))),
        result_kind=str(getattr(result, "kind", UNSET)),
    )


def build_detail(
    path: os.PathLike | str,
    root: Optional[os.PathLike | str] = None,
) -> RunDetail:
    """Build the full manifest, best-point, diagnostic, and count view."""
    original = Path(path).expanduser()
    run_path = original if original.is_dir() else original.parent
    manifest = _read_manifest(original) or {}
    result = load_result(original)
    result_manifest = getattr(result, "manifest", None)
    if (
        not manifest
        and isinstance(result_manifest, Mapping)
        and any(
            key in result_manifest
            for key in ("emrisearch_version", "source", "obs", "statistic", "space", "seeding", "out")
        )
    ):
        manifest = dict(result_manifest)
    try:
        summary_target = (
            run_path
            if original.is_dir() or original.name == STATE_NAME
            else original
        )
        summary = summarize_run(summary_target, root=root)
    except Exception:
        summary = _fallback_summary(run_path, manifest, result)
    space = _space_from_manifest(manifest)
    sigma_table = n_sigma_to_contain(result, space=space)
    best = _best_point(result, space)
    if best.dimensions and sigma_table.rows:
        best = replace(
            best,
            dimensions=tuple(
                replace(row, n_sigma=sigma_table.rows[index].n_sigma)
                for index, row in enumerate(best.dimensions)
            ),
        )
    process_table = best_per_process(result, space=space)
    diagnostics = Diagnostics(
        n_sigma_to_contain=sigma_table,
        best_per_process=process_table,
    )
    try:
        n_samples = int(len(result.samples))
        n_finite = int(np.sum(np.isfinite(np.asarray(result.log_densities, dtype=float))))
    except Exception:
        n_samples = n_finite = 0
    return RunDetail(
        summary=summary,
        path=str(run_path.resolve(strict=False)),
        manifest=dict(manifest),
        manifest_groups=_manifest_groups(manifest, space),
        best=best,
        diagnostics=diagnostics,
        samples=SampleCounts(n_samples=n_samples, n_finite=n_finite),
        result=result,
        param_space=space,
        warnings=tuple(summary.warnings),
    )


# Public compatibility names for code that wants the fallback to look like the
# corresponding upstream objects.  The aliases remain numpy-only.
RunResult = LightRunResult
ParamSpace = LightParamSpace


__all__ = [
    "LightParamSpace", "LightRunResult", "ParamSpace", "RunResult",
    "load_result", "build_detail", "n_sigma_to_contain", "best_per_process",
]
