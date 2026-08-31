"""Generate-only EMRI-C configuration and Python/PBS artifacts.

The module deliberately has a standard-library-only dependency surface.  It
validates the small, canonical EMRI-C configuration that the GUI exposes and
renders deterministic text files.  It never imports the upstream scientific
stack, starts a process, submits a scheduler job, or evaluates a waveform.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import shlex
import tempfile
from typing import Any, Mapping, Optional, Sequence


_SUPPORTED_SOURCE = "emri_c"
_SPACE_NAMES = ("m1", "m2", "a", "p0", "e0")
_SPACE_TRANSFORMS = {
    "m1": "log10",
    "m2": "log10",
    "a": "identity",
    "p0": "identity",
    "e0": "identity",
}
_DEFAULT_BOUNDS = {
    "m1": (6.30, 6.80),
    "m2": (1.70, 2.10),
    "a": (0.80, 0.99),
    "p0": (7.00, 8.00),
    "e0": (0.20, 0.45),
}
_DEFAULT_PBS = {
    "project": "CFP03-CF-051",
    "job_name": "emric_s12",
    "walltime": "24:00:00",
    "gpu_count": 1,
    "cuda_module": "cuda12.4/toolkit/12.4.1",
    "venv_activate": "/home/svu/e1498138/emri_search_uv/.venv/bin/activate",
    "working_directory": "$PBS_O_WORKDIR",
    "log_directory": "logs",
    "python_filename": "run_emri_c_semicoherent.py",
}
_PBS_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_PBS_MODULE_RE = re.compile(r"^[A-Za-z0-9_.+:/-]+$")
_PYTHON_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.py$")
_WALLTIME_RE = re.compile(r"^\d{1,4}:\d{2}:\d{2}$")
_MISSING = object()


@dataclass(frozen=True)
class BoundSpec:
    """One free intrinsic dimension, with bounds in search coordinates."""

    name: str
    transform: str
    lo: float
    hi: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "transform": self.transform,
            "lo": self.lo,
            "hi": self.hi,
        }


@dataclass(frozen=True)
class Artifact:
    """One deterministic text artifact returned by the generation route."""

    filename: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"filename": self.filename, "content": self.content}


@dataclass(frozen=True)
class ArtifactBundle:
    """The Python and PBS artifacts for one normalized configuration."""

    python: Artifact
    pbs: Artifact

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {"python": self.python.to_dict(), "pbs": self.pbs.to_dict()}


@dataclass(frozen=True)
class EMRICConfig:
    """Explicit typed representation of the supported canonical config.

    The nested mappings retain the upstream vocabulary.  ``to_dict`` is the
    wire representation used by the API; the generator accepts that mapping so
    this model remains independent of FastAPI and Pydantic.
    """

    source: Mapping[str, Any]
    obs: Mapping[str, Any]
    noise: Mapping[str, Any]
    modes: Mapping[str, Any]
    statistic: Mapping[str, Any]
    space: Mapping[str, Any]
    sampler: Mapping[str, Any]
    seeding: Mapping[str, Any]
    out: str
    pbs: Mapping[str, Any]
    emrisearch_version: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "emrisearch_version": self.emrisearch_version,
            "source": dict(self.source),
            "obs": dict(self.obs),
            "noise": dict(self.noise),
            "modes": dict(self.modes),
            "statistic": dict(self.statistic),
            "space": dict(self.space),
            "sampler": dict(self.sampler),
            "seeding": dict(self.seeding),
            "out": self.out,
            "pbs": dict(self.pbs),
        }


class ConfigValidationError(ValueError):
    """Validation failure with stable, field-level messages."""

    def __init__(self, errors: Mapping[str, str]):
        self.errors = dict(errors)
        detail = "; ".join(f"{field}: {message}" for field, message in self.errors.items())
        super().__init__(detail or "invalid configuration")

    @property
    def detail(self) -> str:
        return str(self)


class ArtifactPathError(ValueError):
    """An artifact write directory is missing or unsafe."""


class ArtifactConflictError(FileExistsError):
    """A generated artifact already exists and overwrite was not requested."""


def canonical_config(out: str = "") -> dict[str, Any]:
    """Return a fresh canonical EMRI-C config with explicit defaults.

    ``out`` intentionally defaults to the empty string only for UI form
    initialization.  :func:`normalize_config` refuses that value, so an API
    request must explicitly choose the runtime output directory.
    """

    return {
        "emrisearch_version": None,
        "source": {"preset": _SUPPORTED_SOURCE},
        "obs": {
            "T": 8 / 12,
            "dt": 5,
            "tdi_gen": 1,
            "use_gpu": True,
            "pad_output": False,
        },
        "noise": {"add": True, "seed": 42},
        "modes": {
            "ell": 2,
            "n_vals": [-1, 0, 1, 2, 3, 4, 5],
            "M_mode": None,
            "N_traj": 5000,
            "mode_select": None,
        },
        "statistic": {"kind": "semicoherent", "options": {"N_seg": 12}},
        "space": {
            "kind": "intrinsic",
            "free": [
                {
                    "name": name,
                    "transform": _SPACE_TRANSFORMS[name],
                    "lo": _DEFAULT_BOUNDS[name][0],
                    "hi": _DEFAULT_BOUNDS[name][1],
                }
                for name in _SPACE_NAMES
            ],
            "fixed": {},
        },
        "sampler": {
            "n_seed": 10,
            "num_iterations": 5000,
            "init_cov": 1e-2,
            "print_iter": 10,
            "save_every": 500,
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
            "seed": 6342,
        },
        "seeding": {"kind": "internal_lhs", "n": 1000, "batch_size": 10},
        "out": out,
        "pbs": {
            **_DEFAULT_PBS,
            "output_path": out,
        },
    }


# A descriptive alias is convenient for callers that think of the preset as a
# default rather than a canonical fixture.
def default_config(out: str = "") -> dict[str, Any]:
    """Return the canonical EMRI-C defaults."""

    return canonical_config(out=out)


def _mapping(value: Any, field: str, errors: dict[str, str]) -> Mapping[str, Any]:
    if value is _MISSING:
        return {}
    if not isinstance(value, Mapping):
        errors[field] = "must be an object"
        return {}
    return value


def _unknown_fields(
    value: Mapping[str, Any], allowed: set[str], field: str, errors: dict[str, str]
) -> None:
    for key in value:
        if key not in allowed:
            errors[f"{field}.{key}"] = "is not supported by the canonical builder"


def _bool(
    value: Any, field: str, default: bool, errors: dict[str, str]
) -> bool:
    if value is _MISSING:
        return default
    if not isinstance(value, bool):
        errors[field] = "must be true or false"
        return default
    return value


def _number(
    value: Any,
    field: str,
    default: float,
    errors: dict[str, str],
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> float:
    if value is _MISSING:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors[field] = "must be a number"
        return default
    result = float(value)
    if not math.isfinite(result):
        errors[field] = "must be finite"
        return default
    if positive and result <= 0:
        errors[field] = "must be greater than zero"
        return default
    if non_negative and result < 0:
        errors[field] = "must be zero or greater"
        return default
    return result


def _integer(
    value: Any,
    field: str,
    default: int,
    errors: dict[str, str],
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> int:
    if value is _MISSING:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        errors[field] = "must be an integer"
        return default
    if positive and value <= 0:
        errors[field] = "must be greater than zero"
        return default
    if non_negative and value < 0:
        errors[field] = "must be zero or greater"
        return default
    return value


def _path(
    value: Any,
    field: str,
    errors: dict[str, str],
    *,
    required: bool = False,
    allow_pbs_variable: bool = False,
) -> str:
    if value is _MISSING or value is None:
        if required:
            errors[field] = "is required"
        return ""
    if not isinstance(value, str):
        errors[field] = "must be a path string"
        return ""
    result = value.strip()
    if not result:
        errors[field] = "must not be empty"
        return ""
    if "\x00" in result or "\n" in result or "\r" in result:
        errors[field] = "must not contain NUL or newline characters"
        return ""
    if result.startswith("~"):
        errors[field] = "must not start with ~; use an explicit server path"
        return ""
    if allow_pbs_variable and result == "$PBS_O_WORKDIR":
        return result
    # Reject traversal in either common path spelling.  Other relative paths
    # are allowed when explicitly supplied, which keeps PBS log paths portable.
    segments = re.split(r"[/\\]", result)
    if ".." in segments:
        errors[field] = "must not contain parent-directory traversal"
        return ""
    return result


def _string(
    value: Any,
    field: str,
    default: str,
    errors: dict[str, str],
    *,
    required: bool = False,
) -> str:
    if value is _MISSING or value is None:
        if required:
            errors[field] = "is required"
        return default
    if not isinstance(value, str):
        errors[field] = "must be a string"
        return default
    result = value.strip()
    if not result and required:
        errors[field] = "must not be empty"
    if "\x00" in result or "\n" in result or "\r" in result:
        errors[field] = "must not contain NUL or newline characters"
        return default
    return result


def _bounds_value(value: Any) -> Optional[tuple[Any, Any]]:
    if isinstance(value, Mapping):
        if set(value) - {"lo", "hi"}:
            return None
        if "lo" not in value or "hi" not in value:
            return None
        return value["lo"], value["hi"]
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0], value[1]
    return None


def _normalise_space(
    value: Any, errors: dict[str, str]
) -> dict[str, Any]:
    raw = _mapping(value, "space", errors)
    _unknown_fields(raw, {"kind", "free", "bounds", "transforms", "fixed"}, "space", errors)

    kind = raw.get("kind", "intrinsic")
    if kind != "intrinsic":
        errors["space.kind"] = "must be intrinsic; arbitrary spaces are not supported yet"

    fixed = raw.get("fixed", {})
    if not isinstance(fixed, Mapping):
        errors["space.fixed"] = "must be an object"
        fixed = {}
    elif fixed:
        errors["space.fixed"] = "only an empty fixed mapping is supported for intrinsic EMRI-C"
        fixed = {}

    transforms_raw = raw.get("transforms", {})
    if transforms_raw is _MISSING or transforms_raw is None:
        transforms_raw = {}
    if not isinstance(transforms_raw, Mapping):
        errors["space.transforms"] = "must be an object"
        transforms_raw = {}

    bounds_raw = raw.get("bounds", {})
    if bounds_raw is _MISSING or bounds_raw is None:
        bounds_raw = {}
    if not isinstance(bounds_raw, Mapping):
        errors["space.bounds"] = "must be an object"
        bounds_raw = {}

    free_raw = raw.get("free", _MISSING)
    rows: list[Mapping[str, Any]] = []
    if free_raw is not _MISSING:
        if not isinstance(free_raw, (list, tuple)):
            errors["space.free"] = "must be an array"
        else:
            for index, row in enumerate(free_raw):
                if not isinstance(row, Mapping):
                    errors[f"space.free[{index}]"] = "must be an object"
                else:
                    rows.append(row)
    else:
        for name in _SPACE_NAMES:
            bound = bounds_raw.get(name, _DEFAULT_BOUNDS[name])
            pair = _bounds_value(bound)
            if pair is None:
                errors[f"space.bounds.{name}"] = "must contain lo and hi"
                pair = _DEFAULT_BOUNDS[name]
            rows.append(
                {
                    "name": name,
                    "transform": transforms_raw.get(name, _SPACE_TRANSFORMS[name]),
                    "lo": pair[0],
                    "hi": pair[1],
                }
            )

    if len(rows) != len(_SPACE_NAMES):
        errors["space.free"] = "must contain exactly m1, m2, a, p0, and e0 in that order"
        rows = [
            {
                "name": name,
                "transform": _SPACE_TRANSFORMS[name],
                "lo": _DEFAULT_BOUNDS[name][0],
                "hi": _DEFAULT_BOUNDS[name][1],
            }
            for name in _SPACE_NAMES
        ]

    free: list[dict[str, Any]] = []
    names: list[str] = []
    for index, row in enumerate(rows):
        field = f"space.free[{index}]"
        _unknown_fields(row, {"name", "transform", "lo", "hi", "search_coord"}, field, errors)
        name = row.get("name", _MISSING)
        if not isinstance(name, str) or name not in _SPACE_NAMES:
            errors[f"{field}.name"] = "must be one of m1, m2, a, p0, e0"
            name = _SPACE_NAMES[index] if index < len(_SPACE_NAMES) else "m1"
        names.append(name)
        expected_transform = _SPACE_TRANSFORMS[name]
        transform = row.get("transform", expected_transform)
        if transform != expected_transform:
            errors[f"{field}.transform"] = f"must be {expected_transform} for {name}"
            transform = expected_transform
        lo = _number(row.get("lo", _MISSING), f"{field}.lo", _DEFAULT_BOUNDS[name][0], errors)
        hi = _number(row.get("hi", _MISSING), f"{field}.hi", _DEFAULT_BOUNDS[name][1], errors)
        if hi <= lo:
            errors[f"{field}.hi"] = "must be greater than lo"
            lo, hi = _DEFAULT_BOUNDS[name]
        free.append({"name": name, "transform": transform, "lo": lo, "hi": hi})

    if tuple(names) != _SPACE_NAMES:
        errors["space.free"] = "must contain exactly m1, m2, a, p0, and e0 in that order"
        free = [
            {
                "name": name,
                "transform": _SPACE_TRANSFORMS[name],
                "lo": _DEFAULT_BOUNDS[name][0],
                "hi": _DEFAULT_BOUNDS[name][1],
            }
            for name in _SPACE_NAMES
        ]

    return {"kind": "intrinsic", "free": free, "fixed": {}}


def _normalise_modes(value: Any, errors: dict[str, str]) -> dict[str, Any]:
    defaults = canonical_config()["modes"]
    raw = _mapping(value, "modes", errors)
    _unknown_fields(raw, {"ell", "n_vals", "M_mode", "N_traj", "mode_select"}, "modes", errors)
    ell = _integer(raw.get("ell", _MISSING), "modes.ell", defaults["ell"], errors, non_negative=True)
    n_vals_raw = raw.get("n_vals", _MISSING)
    if n_vals_raw is _MISSING:
        n_vals = list(defaults["n_vals"])
    elif not isinstance(n_vals_raw, (list, tuple)) or not n_vals_raw:
        errors["modes.n_vals"] = "must be a non-empty array of integers"
        n_vals = list(defaults["n_vals"])
    else:
        n_vals = []
        for index, item in enumerate(n_vals_raw):
            if isinstance(item, bool) or not isinstance(item, int):
                errors[f"modes.n_vals[{index}]"] = "must be an integer"
            else:
                n_vals.append(item)
        if not n_vals:
            n_vals = list(defaults["n_vals"])
    m_mode = raw.get("M_mode", _MISSING)
    if m_mode is _MISSING or m_mode is None:
        normalized_m_mode = None
    else:
        normalized_m_mode = _integer(m_mode, "modes.M_mode", 1, errors, positive=True)
    n_traj = _integer(raw.get("N_traj", _MISSING), "modes.N_traj", defaults["N_traj"], errors, positive=True)
    mode_select = raw.get("mode_select", _MISSING)
    if mode_select is _MISSING or mode_select is None:
        normalized_mode_select = None
    else:
        normalized_mode_select = []
        if not isinstance(mode_select, (list, tuple)):
            errors["modes.mode_select"] = "must be null or an array of mode groups"
            normalized_mode_select = None
        else:
            for group_index, group in enumerate(mode_select):
                if not isinstance(group, (list, tuple)):
                    errors[f"modes.mode_select[{group_index}]"] = "must be an array"
                    continue
                normalized_group = []
                for mode_index, mode in enumerate(group):
                    if not isinstance(mode, (list, tuple)) or len(mode) != 3:
                        errors[
                            f"modes.mode_select[{group_index}][{mode_index}]"
                        ] = "must be a three-integer mode"
                        continue
                    if any(isinstance(item, bool) or not isinstance(item, int) for item in mode):
                        errors[
                            f"modes.mode_select[{group_index}][{mode_index}]"
                        ] = "must be a three-integer mode"
                        continue
                    normalized_group.append(list(mode))
                normalized_mode_select.append(normalized_group)
    return {
        "ell": ell,
        "n_vals": n_vals,
        "M_mode": normalized_m_mode,
        "N_traj": n_traj,
        "mode_select": normalized_mode_select,
    }


def _normalise_sampler(value: Any, errors: dict[str, str]) -> dict[str, Any]:
    defaults = canonical_config()["sampler"]
    raw = _mapping(value, "sampler", errors)
    allowed = set(defaults)
    _unknown_fields(raw, allowed, "sampler", errors)
    integer_fields = {
        "n_seed": True,
        "num_iterations": True,
        "print_iter": True,
        "save_every": False,
        "alpha": True,
        "trail_size": True,
        "integral_num": True,
        "gamma": True,
    }
    normalized: dict[str, Any] = {}
    for field, positive in integer_fields.items():
        normalized[field] = _integer(
            raw.get(field, _MISSING),
            f"sampler.{field}",
            defaults[field],
            errors,
            positive=positive,
            non_negative=not positive,
        )
    normalized["init_cov"] = _number(
        raw.get("init_cov", _MISSING),
        "sampler.init_cov",
        defaults["init_cov"],
        errors,
        positive=True,
    )
    normalized["merge_confidence"] = _number(
        raw.get("merge_confidence", _MISSING),
        "sampler.merge_confidence",
        defaults["merge_confidence"],
        errors,
        positive=True,
    )
    if normalized["merge_confidence"] > 1:
        errors["sampler.merge_confidence"] = "must be at most 1"
        normalized["merge_confidence"] = defaults["merge_confidence"]
    normalized["boundary_limiting"] = _bool(
        raw.get("boundary_limiting", _MISSING),
        "sampler.boundary_limiting",
        defaults["boundary_limiting"],
        errors,
    )
    normalized["use_beta"] = _bool(raw.get("use_beta", _MISSING), "sampler.use_beta", defaults["use_beta"], errors)
    normalized["use_pool"] = _bool(raw.get("use_pool", _MISSING), "sampler.use_pool", defaults["use_pool"], errors)
    normalized["keep_dead_processes"] = _bool(
        raw.get("keep_dead_processes", _MISSING),
        "sampler.keep_dead_processes",
        defaults["keep_dead_processes"],
        errors,
    )
    exclude = raw.get("exclude_scale_z", _MISSING)
    if exclude is _MISSING or exclude == "inf":
        normalized["exclude_scale_z"] = "inf"
    elif isinstance(exclude, str):
        errors["sampler.exclude_scale_z"] = "must be the string inf or a finite non-negative number"
        normalized["exclude_scale_z"] = "inf"
    else:
        normalized["exclude_scale_z"] = _number(
            exclude,
            "sampler.exclude_scale_z",
            0.0,
            errors,
            non_negative=True,
        )
    seed = raw.get("seed", _MISSING)
    if seed is _MISSING or seed is None:
        normalized["seed"] = None
    else:
        normalized["seed"] = _integer(seed, "sampler.seed", defaults["seed"], errors, non_negative=True)
    # Keep the public order identical to SamplerSpec's manifest vocabulary.
    return {
        "n_seed": normalized["n_seed"],
        "num_iterations": normalized["num_iterations"],
        "init_cov": normalized["init_cov"],
        "print_iter": normalized["print_iter"],
        "save_every": normalized["save_every"],
        "merge_confidence": normalized["merge_confidence"],
        "alpha": normalized["alpha"],
        "trail_size": normalized["trail_size"],
        "boundary_limiting": normalized["boundary_limiting"],
        "use_beta": normalized["use_beta"],
        "integral_num": normalized["integral_num"],
        "gamma": normalized["gamma"],
        "exclude_scale_z": normalized["exclude_scale_z"],
        "use_pool": normalized["use_pool"],
        "keep_dead_processes": normalized["keep_dead_processes"],
        "seed": normalized["seed"],
    }


def _normalise_pbs(value: Any, out: str, errors: dict[str, str]) -> dict[str, Any]:
    defaults = {**_DEFAULT_PBS, "output_path": out}
    if value is _MISSING:
        # The whole PBS block is optional: preset defaults fill it entirely.
        return defaults
    raw = _mapping(value, "pbs", errors)
    _unknown_fields(raw, set(defaults), "pbs", errors)
    project = _string(raw.get("project", _MISSING), "pbs.project", defaults["project"], errors, required=False)
    if not _PBS_NAME_RE.fullmatch(project):
        errors["pbs.project"] = "must contain only letters, digits, underscore, dot, colon, or hyphen"
        project = defaults["project"]
    job_name = _string(raw.get("job_name", _MISSING), "pbs.job_name", defaults["job_name"], errors, required=False)
    if not _PBS_NAME_RE.fullmatch(job_name):
        errors["pbs.job_name"] = "must contain only letters, digits, underscore, dot, colon, or hyphen"
        job_name = defaults["job_name"]
    walltime = _string(raw.get("walltime", _MISSING), "pbs.walltime", defaults["walltime"], errors, required=False)
    if not _WALLTIME_RE.fullmatch(walltime):
        errors["pbs.walltime"] = "must use HH:MM:SS"
        walltime = defaults["walltime"]
    else:
        hours, minutes, seconds = (int(part) for part in walltime.split(":"))
        if minutes > 59 or seconds > 59:
            errors["pbs.walltime"] = "must use valid minutes and seconds"
            walltime = defaults["walltime"]
    gpu_count = _integer(raw.get("gpu_count", _MISSING), "pbs.gpu_count", defaults["gpu_count"], errors, positive=True)
    cuda_module = _string(
        raw.get("cuda_module", _MISSING),
        "pbs.cuda_module",
        defaults["cuda_module"],
        errors,
        required=False,
    )
    if not _PBS_MODULE_RE.fullmatch(cuda_module):
        errors["pbs.cuda_module"] = "must be a safe module name"
        cuda_module = defaults["cuda_module"]
    venv_activate = _path(
        raw.get("venv_activate", _MISSING),
        "pbs.venv_activate",
        errors,
        required=False,
    )
    if not venv_activate:
        venv_activate = defaults["venv_activate"]
    working_directory = _path(
        raw.get("working_directory", _MISSING),
        "pbs.working_directory",
        errors,
        required=False,
        allow_pbs_variable=True,
    )
    if not working_directory:
        working_directory = defaults["working_directory"]
    log_directory = _path(
        raw.get("log_directory", _MISSING),
        "pbs.log_directory",
        errors,
        required=False,
    )
    if not log_directory:
        log_directory = defaults["log_directory"]
    python_filename = _string(
        raw.get("python_filename", _MISSING),
        "pbs.python_filename",
        defaults["python_filename"],
        errors,
        required=False,
    )
    if not _PYTHON_FILENAME_RE.fullmatch(python_filename):
        errors["pbs.python_filename"] = "must be a simple .py filename without directories"
        python_filename = defaults["python_filename"]
    output_path = _path(raw.get("output_path", _MISSING), "pbs.output_path", errors, required=False)
    if not output_path:
        output_path = out
    if output_path != out:
        errors["pbs.output_path"] = "must match config out"
        output_path = out
    return {
        "project": project,
        "job_name": job_name,
        "walltime": walltime,
        "gpu_count": gpu_count,
        "cuda_module": cuda_module,
        "venv_activate": venv_activate,
        "working_directory": working_directory,
        "log_directory": log_directory,
        "output_path": output_path,
        "python_filename": python_filename,
    }


def normalize_config(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one request config without importing numpy.

    The accepted surface is intentionally limited to the canonical EMRI-C
    preset.  Partial nested objects are merged with explicit preset defaults;
    unsupported keys are reported as field-level errors.
    """

    if not isinstance(payload, Mapping):
        raise ConfigValidationError({"config": "must be an object"})
    errors: dict[str, str] = {}
    allowed = {
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
        "pbs",
    }
    _unknown_fields(payload, allowed, "config", errors)
    defaults = canonical_config()

    version = payload.get("emrisearch_version", None)
    if version is not None:
        version = _string(version, "emrisearch_version", "", errors, required=True) or None

    source_raw = payload.get("source", _MISSING)
    if isinstance(source_raw, str):
        source_preset = source_raw.strip()
    else:
        source_map = _mapping(source_raw, "source", errors)
        _unknown_fields(source_map, {"preset"}, "source", errors)
        source_preset = source_map.get("preset", _SUPPORTED_SOURCE)
    if source_preset != _SUPPORTED_SOURCE:
        errors["source.preset"] = "must be exactly emri_c"
        source_preset = _SUPPORTED_SOURCE

    obs_raw = _mapping(payload.get("obs", _MISSING), "obs", errors)
    _unknown_fields(obs_raw, {"T", "dt", "tdi_gen", "use_gpu", "pad_output"}, "obs", errors)
    obs = {
        "T": _number(obs_raw.get("T", _MISSING), "obs.T", defaults["obs"]["T"], errors, positive=True),
        "dt": _number(obs_raw.get("dt", _MISSING), "obs.dt", defaults["obs"]["dt"], errors, positive=True),
        "tdi_gen": _integer(obs_raw.get("tdi_gen", _MISSING), "obs.tdi_gen", 1, errors),
        "use_gpu": _bool(obs_raw.get("use_gpu", _MISSING), "obs.use_gpu", True, errors),
        "pad_output": _bool(obs_raw.get("pad_output", _MISSING), "obs.pad_output", False, errors),
    }
    if obs["dt"] > 10:
        errors["obs.dt"] = "must be at most 10 seconds for the upstream response buffer"
        obs["dt"] = defaults["obs"]["dt"]
    if obs["tdi_gen"] not in (1, 2):
        errors["obs.tdi_gen"] = "must be 1 or 2"
        obs["tdi_gen"] = 1

    noise_raw = _mapping(payload.get("noise", _MISSING), "noise", errors)
    _unknown_fields(noise_raw, {"add", "seed"}, "noise", errors)
    noise = {
        "add": _bool(noise_raw.get("add", _MISSING), "noise.add", True, errors),
        "seed": _integer(noise_raw.get("seed", _MISSING), "noise.seed", 42, errors, non_negative=True),
    }

    modes = _normalise_modes(payload.get("modes", _MISSING), errors)

    statistic_raw = _mapping(payload.get("statistic", _MISSING), "statistic", errors)
    _unknown_fields(statistic_raw, {"kind", "options"}, "statistic", errors)
    statistic_kind = statistic_raw.get("kind", "semicoherent")
    if statistic_kind != "semicoherent":
        errors["statistic.kind"] = "must be semicoherent for the canonical EMRI-C builder"
        statistic_kind = "semicoherent"
    options_raw = statistic_raw.get("options", {"N_seg": 12})
    options = _mapping(options_raw, "statistic.options", errors)
    _unknown_fields(options, {"N_seg"}, "statistic.options", errors)
    n_seg = _integer(options.get("N_seg", _MISSING), "statistic.options.N_seg", 12, errors, positive=True)
    statistic = {"kind": statistic_kind, "options": {"N_seg": n_seg}}

    space = _normalise_space(payload.get("space", _MISSING), errors)
    sampler = _normalise_sampler(payload.get("sampler", _MISSING), errors)

    seeding_raw = _mapping(payload.get("seeding", _MISSING), "seeding", errors)
    _unknown_fields(seeding_raw, {"kind", "n", "batch_size"}, "seeding", errors)
    seeding_kind = seeding_raw.get("kind", "internal_lhs")
    if seeding_kind != "internal_lhs":
        errors["seeding.kind"] = "must be internal_lhs for the canonical builder"
        seeding_kind = "internal_lhs"
    seeding = {
        "kind": seeding_kind,
        "n": _integer(seeding_raw.get("n", _MISSING), "seeding.n", 1000, errors, positive=True),
        "batch_size": _integer(
            seeding_raw.get("batch_size", _MISSING),
            "seeding.batch_size",
            10,
            errors,
            positive=True,
        ),
    }

    out = _path(payload.get("out", _MISSING), "out", errors, required=True)
    if not out:
        out = ""
    pbs = _normalise_pbs(payload.get("pbs", _MISSING), out, errors)

    if errors:
        raise ConfigValidationError(errors)
    config = EMRICConfig(
        emrisearch_version=version,
        source={"preset": source_preset},
        obs=obs,
        noise=noise,
        modes=modes,
        statistic=statistic,
        space=space,
        sampler=sampler,
        seeding=seeding,
        out=out,
        pbs=pbs,
    )
    return config.to_dict()


def _py_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isinf(value):
            return "float('-inf')" if value < 0 else "float('inf')"
        if math.isclose(value, 8 / 12, rel_tol=0.0, abs_tol=1e-15):
            return "8 / 12"
        if math.isclose(value, 1e-2, rel_tol=0.0, abs_tol=1e-15):
            return "1e-2"
        return repr(value)
    return json.dumps(value, ensure_ascii=True, separators=(", ", ": "))


def _python_artifact(config: Mapping[str, Any]) -> Artifact:
    source = config["source"]["preset"]
    obs = config["obs"]
    space = config["space"]
    statistic = config["statistic"]
    noise = config["noise"]
    modes = config["modes"]
    sampler = config["sampler"]
    seeding = config["seeding"]
    out = config["out"]
    pbs = config["pbs"]

    bound_lines = [
        f'        {_py_literal(row["name"])}: ({_py_literal(row["lo"])}, {_py_literal(row["hi"])}),'
        for row in space["free"]
    ]
    sampler_fields = (
        "n_seed", "num_iterations", "init_cov", "print_iter", "save_every",
        "merge_confidence", "alpha", "trail_size", "boundary_limiting", "use_beta",
        "integral_num", "gamma", "exclude_scale_z", "use_pool",
        "keep_dead_processes", "seed",
    )
    sampler_lines = []
    for field in sampler_fields:
        value = sampler[field]
        if field == "exclude_scale_z" and value == "inf":
            value = float("inf")
        sampler_lines.append(
            f"            {field}={_py_literal(value)},"
        )

    lines = [
        "#!/usr/bin/env python3",
        '"""Generated EMRI-C run artifact; inspect before running on a compatible node."""',
        "from __future__ import annotations",
        "",
        "import os",
        "",
        "# The configured path is the fallback; EMRISEARCH_OUT is an explicit runtime override.",
        f"OUT = os.environ.get('EMRISEARCH_OUT', {_py_literal(out)})",
        "",
        "",
        "def main():",
        "    import few",
        "    from emrisearch import ParamSpace, load_mojito",
        "    from emrisearch.config import ModeConfig, NoiseConfig, ObsConfig, SamplerSpec",
        "    from emrisearch.run import ParisRun, internal_lhs",
        "",
        '    few.get_config_setter(reset=True).set_log_level("info")',
        "",
        "    # Injected source from the upstream MOJITO catalogue.",
        f"    source = load_mojito({_py_literal(source)})",
        "",
        "    obs = ObsConfig(",
        f"        T={_py_literal(obs['T'])}, dt={_py_literal(obs['dt'])}, tdi_gen={_py_literal(obs['tdi_gen'])}, "
        f"use_gpu={_py_literal(obs['use_gpu'])}, pad_output={_py_literal(obs['pad_output'])},",
        "    )",
        "",
        "    # Bounds are in search coordinates: log10 for m1/m2, identity otherwise.",
        "    space = ParamSpace.intrinsic(source, box={",
        *bound_lines,
        "    })",
        "",
        "    if not space.contains_truth:",
        "        raise SystemExit(",
        '            f"injected source lies outside the prior box in {space.truth_outside()}"',
        "        )",
        "",
        "    run = ParisRun(",
        "        source=source,",
        "        obs=obs,",
        "        space=space,",
        "        out=OUT,",
        f"        statistic={_py_literal(statistic['kind'])}, "
        ,
        
        f"        stat_opts={_py_literal(statistic['options'])}, "
        ,
        
        f"        noise=NoiseConfig(add={_py_literal(noise['add'])}, seed={_py_literal(noise['seed'])}), "
        ,
        
        "        modes=ModeConfig(",
        f"            ell={_py_literal(modes['ell'])}, n_vals={_py_literal(modes['n_vals'])}, "
        ,
        
        f"            M_mode={_py_literal(modes['M_mode'])}, N_traj={_py_literal(modes['N_traj'])}, "
        ,
        
        f"            mode_select={_py_literal(modes['mode_select'])}, "
        ,
        
        "        ),",
        "        sampler=SamplerSpec(",
        *sampler_lines,
        "        ),",
        f"        seeding=internal_lhs(n={_py_literal(seeding['n'])}, batch_size={_py_literal(seeding['batch_size'])}),",
        "    )",
        "",
        "    print(run)",
        "    run.execute()",
        "",
        "",
        'if __name__ == "__main__":',
        "    main()",
        "",
    ]
    return Artifact(
        filename=str(pbs["python_filename"]),
        content="\n".join(line.rstrip() for line in lines),
    )


def _shell_path(value: str) -> str:
    # Keep PBS_O_WORKDIR executable as an intentional PBS variable.  All other
    # paths are quoted through the standard-library shell quoting routine.
    if value == "$PBS_O_WORKDIR":
        return '"$PBS_O_WORKDIR"'
    return shlex.quote(value)


def _join_path(directory: str, filename: str) -> str:
    if directory.endswith("/"):
        return f"{directory}{filename}"
    return f"{directory}/{filename}"


def _pbs_artifact(config: Mapping[str, Any]) -> Artifact:
    pbs = config["pbs"]
    out = config["out"]
    python_filename = pbs["python_filename"]
    log_directory = pbs["log_directory"]
    job_name = pbs["job_name"]
    log_out = _join_path(log_directory, f"{job_name}.out")
    log_err = _join_path(log_directory, f"{job_name}.err")
    working_directory = pbs["working_directory"]
    lines = [
        "#!/bin/bash",
        "# Generated PBS artifact. Submission is intentionally deferred to the human operator.",
        f"#PBS -P {pbs['project']}",
        f"#PBS -o {_shell_path(log_out)}",
        f"#PBS -e {_shell_path(log_err)}",
        f"#PBS -N {pbs['job_name']}",
        f"#PBS -l walltime={pbs['walltime']}",
        f"#PBS -l select=1:ngpus={pbs['gpu_count']}",
        "",
        f"cd {_shell_path(working_directory)}",
        f"mkdir -p {_shell_path(log_directory)}",
        "",
        f"module load {shlex.quote(pbs['cuda_module'])}",
        f"source {_shell_path(pbs['venv_activate'])}",
        "",
        f"export EMRISEARCH_OUT={_shell_path(out)}",
        f"python -u {_shell_path(python_filename)}",
        "",
    ]
    return Artifact(filename="run_emri_c_semicoherent.pbs", content="\n".join(lines))


def build_artifacts(config: Mapping[str, Any]) -> ArtifactBundle:
    """Build deterministic artifacts for a valid config mapping."""

    normalized = normalize_config(config)
    return ArtifactBundle(
        python=_python_artifact(normalized),
        pbs=_pbs_artifact(normalized),
    )


def _write_text_no_overwrite(path: Path, content: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            descriptor = -1
            handle.write(content)
    finally:
        if descriptor != -1:
            os.close(descriptor)


def _write_text_replace(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def write_artifacts(
    artifacts: ArtifactBundle,
    artifact_dir: str,
    *,
    overwrite: bool = False,
) -> list[str]:
    """Write both artifacts to an explicit directory and return exact paths."""

    errors: dict[str, str] = {}
    directory = _path(artifact_dir, "artifact_dir", errors, required=True)
    if not isinstance(overwrite, bool):
        errors["overwrite"] = "must be true or false"
    if errors:
        raise ConfigValidationError(errors)
    target_dir = Path(directory)
    if target_dir.exists() and not target_dir.is_dir():
        raise ArtifactPathError(f"artifact_dir is not a directory: {artifact_dir}")
    targets = [target_dir / artifacts.python.filename, target_dir / artifacts.pbs.filename]
    if not overwrite:
        existing = [str(path) for path in targets if path.exists()]
        if existing:
            raise ArtifactConflictError(
                "artifact already exists: " + ", ".join(existing) + "; set overwrite=true to replace it"
            )
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArtifactPathError(f"could not create artifact_dir {artifact_dir}: {exc}") from exc

    written: list[Path] = []
    try:
        if overwrite:
            _write_text_replace(targets[0], artifacts.python.content)
            written.append(targets[0])
            _write_text_replace(targets[1], artifacts.pbs.content)
            written.append(targets[1])
        else:
            _write_text_no_overwrite(targets[0], artifacts.python.content)
            written.append(targets[0])
            _write_text_no_overwrite(targets[1], artifacts.pbs.content)
            written.append(targets[1])
    except FileExistsError as exc:
        for path in written:
            try:
                path.unlink()
            except OSError:
                pass
        raise ArtifactConflictError(
            "artifact already exists; set overwrite=true to replace it"
        ) from exc
    except OSError as exc:
        raise ArtifactPathError(f"could not write generated artifacts: {exc}") from exc
    return [str(path) for path in written]


def generate_config_artifacts(
    payload: Mapping[str, Any],
    *,
    artifact_dir: Optional[str] = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Normalize, render, and optionally write artifacts without execution."""

    normalized = normalize_config(payload)
    bundle = ArtifactBundle(
        python=_python_artifact(normalized),
        pbs=_pbs_artifact(normalized),
    )
    written_paths: list[str] = []
    if artifact_dir is not None:
        written_paths = write_artifacts(bundle, artifact_dir, overwrite=overwrite)
    return {
        "config": normalized,
        "artifacts": bundle.to_dict(),
        "written_paths": written_paths,
    }


__all__ = [
    "Artifact",
    "ArtifactBundle",
    "ArtifactConflictError",
    "ArtifactPathError",
    "BoundSpec",
    "ConfigValidationError",
    "EMRICConfig",
    "build_artifacts",
    "canonical_config",
    "default_config",
    "generate_config_artifacts",
    "normalize_config",
    "write_artifacts",
]
