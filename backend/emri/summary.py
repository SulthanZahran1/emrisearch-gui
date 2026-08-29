"""Fast, pickle-avoiding summaries for the run list.

A manifest-backed summary never opens ``sampler_state.pkl``.  This is the
important performance boundary for the explorer: scanning a large tree must
not deserialize live PARIS samplers.  Legacy tuple/dict/NPZ files are small
and self-describing enough for an inexpensive best-value pass; unknown (and
especially PARIS) pickle objects are left to :mod:`emri.detail`.
"""
from __future__ import annotations

import json
import os
import pickle
import pickletools
import zipfile
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

import numpy as np

from .root import resolve_run_root, resolve_run_roots
from .types import RunSummary, UNSET

MANIFEST_NAME = "manifest.json"
STATE_NAME = "sampler_state.pkl"


def _as_path(path: os.PathLike | str) -> Path:
    return Path(path).expanduser()


def _run_directory(path: Path) -> Path:
    if path.is_dir():
        return path
    if path.is_file() or path.name == STATE_NAME or path.suffix == ".npz":
        return path.parent
    return path


def _summary_id(run_path: Path, root: Optional[os.PathLike | str]) -> str:
    candidate = run_path.resolve(strict=False)
    if root is not None:
        roots = (Path(root).expanduser().resolve(strict=False),)
    else:
        try:
            roots = resolve_run_roots()
        except (OSError, ValueError):
            try:
                primary = resolve_run_root()
            except (OSError, ValueError):
                primary = None
            roots = (
                (Path(primary).expanduser().resolve(strict=False),)
                if primary is not None
                else ()
            )
    for root_path in roots:
        try:
            relative = candidate.relative_to(root_path)
        except ValueError:
            continue
        return relative.as_posix() or candidate.name
    return candidate.name


def _finite_max(values: Any) -> Optional[float]:
    try:
        array = np.asarray(values, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    if array.size == 0:
        return None
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return None
    return float(np.max(finite))


def _manifest_best(manifest: Mapping[str, Any]) -> Optional[float]:
    """Read an optional cheap best value without consulting the state file."""
    candidates = [
        manifest.get("best_log_density"),
        manifest.get("best_ld"),
    ]
    for container_name in ("best", "result", "summary", "sampler"):
        container = manifest.get(container_name)
        if isinstance(container, Mapping):
            candidates.extend(
                [container.get("best_log_density"), container.get("best_ld")]
            )
            best = container.get("best")
            if isinstance(best, Mapping):
                candidates.extend(
                    [best.get("log_density"), best.get("ld"), best.get("value")]
                )
    for value in candidates:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            return number
    return None


def _manifest_ndim(manifest: Mapping[str, Any]) -> Optional[int]:
    space = manifest.get("space")
    if not isinstance(space, Mapping):
        return None
    free = space.get("free")
    if not isinstance(free, (list, tuple)):
        return None
    return len(free)


def _manifest_summary(run_path: Path, manifest: Mapping[str, Any], root) -> RunSummary:
    seeding = manifest.get("seeding")
    seeding = seeding if isinstance(seeding, Mapping) else {}
    statistic = manifest.get("statistic")
    if isinstance(statistic, Mapping):
        statistic_name = statistic.get("kind", UNSET)
    elif isinstance(statistic, str):
        statistic_name = statistic
    else:
        statistic_name = UNSET
    kind = seeding.get("kind", UNSET)
    from_run = seeding.get("path") if kind == "from_run" else None
    out = manifest.get("out")
    return RunSummary(
        id=_summary_id(run_path, root),
        path=str(run_path.resolve(strict=False)),
        kind=str(kind) if kind is not None else UNSET,
        statistic=str(statistic_name) if statistic_name is not None else UNSET,
        ndim=_manifest_ndim(manifest),
        best_log_density=_manifest_best(manifest),
        from_run=str(from_run) if from_run not in (None, "") else None,
        out=str(out) if out not in (None, "") else None,
        result_kind=UNSET,
    )


def _known_arrays(obj: Any) -> Optional[Tuple[str, Any, Any]]:
    if isinstance(obj, tuple) and len(obj) == 2:
        return "lhs_tuple", obj[0], obj[1]
    if isinstance(obj, Mapping):
        for points_key, values_key in (
            ("lhs_phys", "log_densities"),
            ("phys_pts", "det_snr"),
            ("samples", "log_densities"),
        ):
            if points_key in obj and values_key in obj:
                return "lhs_dict", obj[points_key], obj[values_key]
    return None


def _arrays_summary(kind: str, points: Any, values: Any) -> Tuple[Optional[int], Optional[float]]:
    try:
        array = np.asarray(points, dtype=float)
        if array.ndim == 1:
            ndim = int(array.shape[0])
        elif array.ndim == 2:
            ndim = int(array.shape[1])
        else:
            return None, None
    except (TypeError, ValueError):
        return None, None
    return ndim, _finite_max(values)


def _npz_summary(path: Path) -> Optional[Tuple[str, Optional[int], Optional[float]]]:
    try:
        with np.load(path, allow_pickle=False) as data:
            keys = set(data.files)
            for points_key, values_key in (
                ("samples", "log_densities"),
                ("lhs_phys", "log_densities"),
                ("phys_pts", "det_snr"),
            ):
                if points_key in keys and values_key in keys:
                    ndim, best = _arrays_summary("npz", data[points_key], data[values_key])
                    return "npz", ndim, best
            if "x_map" in keys:
                points = np.asarray(data["x_map"], dtype=float)
                ndim = int(points.size) if points.ndim <= 1 else int(points.shape[-1])
                best = _finite_max(data["lnL_map"]) if "lnL_map" in keys else None
                return "npz_map", ndim, best
    except (OSError, ValueError, TypeError, zipfile.BadZipFile):
        return None
    return None


def _pickle_container_kind(data: bytes) -> Optional[str]:
    """Classify cheap top-level pickle containers without constructing objects.

    Upstream sampler pickles are arbitrary object graphs and must remain outside
    the summary path.  ``pickletools`` lets us distinguish the legacy tuple and
    dict wire shapes from those graphs before calling ``pickle.loads``.  The
    final container opcode is followed by only memo bookkeeping in normal
    pickle protocols; malformed streams simply return ``None``.
    """
    try:
        operations = list(pickletools.genops(data))
    except Exception:
        return None
    ignored = {"STOP", "MEMOIZE", "FRAME", "PUT", "BINPUT", "LONG_BINPUT"}
    for operation, _argument, _position in reversed(operations):
        if operation.name in ignored:
            continue
        if operation.name in {"TUPLE", "TUPLE1", "TUPLE2", "TUPLE3"}:
            return "lhs_tuple"
        if operation.name in {"SETITEM", "SETITEMS"}:
            return "lhs_dict"
        return None
    return None


def _cheap_pickle_summary(path: Path) -> Optional[Tuple[str, Optional[int], Optional[float]]]:
    try:
        data = path.read_bytes()
    except OSError:
        return None

    # A live PARIS sampler can be enormous and may require unavailable callable
    # globals during unpickling.  The module marker is enough to keep the fast
    # path from touching the known upstream sampler shape.
    lowered = data.lower()
    if b"parismc" in lowered or b"paris_sampler" in lowered:
        return None

    # NPZ is a ZIP container even when a fixture deliberately keeps the
    # upstream STATE_NAME filename.  This check avoids pickle.load on it.
    if data[:4] == b"PK\x03\x04":
        return _npz_summary(path)

    container_kind = _pickle_container_kind(data)
    if container_kind is None:
        return None
    try:
        obj = pickle.loads(data)
    except Exception:
        return None
    known = _known_arrays(obj)
    if known is None or known[0] != container_kind:
        return None
    kind, points, values = known
    ndim, best = _arrays_summary(kind, points, values)
    return kind, ndim, best


def summarize_run(
    path: os.PathLike | str,
    root: Optional[os.PathLike | str] = None,
) -> RunSummary:
    """Return a run-list summary for a directory or a supported result file.

    ``root`` controls the relative id.  If omitted, the configured primary or
    registered add-run root is used when the path is beneath it; otherwise the
    basename is used.
    The manifest branch reads only JSON and is deliberately independent of the
    pickle, matching upstream ``io.py:152-158`` and ``io.py:168-172``.
    """
    original = _as_path(path)
    run_path = _run_directory(original)
    if not run_path.exists():
        raise FileNotFoundError(str(path))

    manifest_path = (
        run_path / MANIFEST_NAME if run_path.is_dir() else run_path.parent / MANIFEST_NAME
    )
    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"could not read manifest {manifest_path}: {exc}") from exc
        if not isinstance(manifest, Mapping):
            raise ValueError(f"manifest {manifest_path} must contain a JSON object")
        # Do not even stat/open STATE_NAME in this branch.  In particular, this
        # remains safe for a half-written or unpickleable sampler checkpoint.
        return _manifest_summary(run_path, manifest, root)

    if original.is_file() and (
        original.suffix == ".npz" or original.name != STATE_NAME
    ):
        state_path = original
    elif run_path.is_dir():
        state_path = run_path / STATE_NAME
    else:
        state_path = original
    if not state_path.exists():
        raise FileNotFoundError(f"{run_path!s} contains no {STATE_NAME} or {MANIFEST_NAME}")
    cheap = _cheap_pickle_summary(state_path)
    result_kind, ndim, best = (cheap or (UNSET, None, None))
    return RunSummary(
        id=_summary_id(run_path, root),
        path=str(run_path.resolve(strict=False)),
        kind="legacy",
        statistic=UNSET,
        ndim=ndim,
        best_log_density=best,
        from_run=None,
        out=str(run_path.resolve(strict=False)),
        result_kind=result_kind,
    )


__all__ = ["MANIFEST_NAME", "STATE_NAME", "summarize_run"]
