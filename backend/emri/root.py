"""Local run-root resolution and persistent add-run configuration.

The GUI is local-first: an explicit ``EMRISEARCH_ROOT`` environment variable
wins, otherwise the optional ``backend/config.json`` file supplies a primary
``run_root`` and persistent ``extra_runs``.  The helpers use one process-local
re-entrant lock and an atomic replace for writes.  This is intentionally
thread-safe enough for the single-process backend; it is not a multi-process
configuration store.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, Union


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
_ENV_NAME = "EMRISEARCH_ROOT"
_CONFIG_LOCK = threading.RLock()

PathLike = Union[str, os.PathLike]


def _path_arg(path: Optional[PathLike]) -> Path:
    return Path(path) if path is not None else Path(CONFIG_PATH)


def _normalise_config(config: Optional[Mapping[str, Any]]) -> dict:
    """Return a copy with the two public keys in predictable shapes."""
    if config is None:
        config = {}
    if not isinstance(config, Mapping):
        raise ValueError("run-root config must be a JSON object")
    result = dict(config)
    run_root = result.get("run_root")
    result["run_root"] = None if run_root in (None, "") else str(run_root)
    extra = result.get("extra_runs", [])
    if extra is None:
        extra = []
    if not isinstance(extra, (list, tuple)):
        raise ValueError("run-root config extra_runs must be a list")
    result["extra_runs"] = [str(value) for value in extra if value not in (None, "")]
    return result


def load_config(path: Optional[PathLike] = None) -> dict:
    """Load the optional config, returning an empty normalized config if absent.

    Parameters
    ----------
    path:
        Primarily useful for tests and embedding.  The default is
        ``backend/config.json`` next to this package.
    """
    config_path = _path_arg(path)
    with _CONFIG_LOCK:
        if not config_path.exists():
            return {"run_root": None, "extra_runs": []}
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {config_path}: {exc}") from exc
        return _normalise_config(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    return value


def save_config(config: Mapping[str, Any], path: Optional[PathLike] = None) -> dict:
    """Atomically save and return a normalized run-root config.

    The lock protects concurrent threads in this backend process.  A temporary
    file in the destination directory plus ``os.replace`` prevents readers
    from observing a partially written JSON document.
    """
    config_path = _path_arg(path)
    normalized = _normalise_config(config)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_value(normalized)
    with _CONFIG_LOCK:
        fd, temporary = tempfile.mkstemp(
            prefix=f".{config_path.name}.", suffix=".tmp", dir=str(config_path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, config_path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return normalized


def _resolved_path(value: PathLike, base: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=False)


def resolve_run_root(config_path: Optional[PathLike] = None) -> Optional[Path]:
    """Resolve the primary run root, with ``EMRISEARCH_ROOT`` taking priority.

    An unset/empty environment variable is treated as absent.  This function
    returns only the primary configured root; use :func:`resolve_run_roots` to
    obtain that root plus registered add-run paths.
    """
    env_value = os.environ.get(_ENV_NAME, "").strip()
    if env_value:
        return _resolved_path(env_value, Path.cwd())
    config_file = _path_arg(config_path)
    config = load_config(config_file)
    value = config.get("run_root")
    if value in (None, ""):
        return None
    return _resolved_path(value, config_file.parent)


def resolve_run_roots(config_path: Optional[PathLike] = None) -> tuple[Path, ...]:
    """Resolve all roots to scan, deduplicated while retaining config order.

    When ``EMRISEARCH_ROOT`` is set it overrides the primary root, while
    persistent ``extra_runs`` still overlay the scan as registered add-run
    paths.
    """
    env_value = os.environ.get(_ENV_NAME, "").strip()
    config_file = _path_arg(config_path)
    if env_value:
        values = [_resolved_path(env_value, Path.cwd())]
        try:
            config = load_config(config_file)
        except (OSError, ValueError):
            config = {"extra_runs": []}
    else:
        config = load_config(config_file)
        values = []
        if config.get("run_root") not in (None, ""):
            values.append(config["run_root"])
    values.extend(config.get("extra_runs", []))
    result = []
    seen = set()
    for value in values:
        resolved = value if isinstance(value, Path) else _resolved_path(value, config_file.parent)
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return tuple(result)


# A descriptive alias for API callers that think in terms of all configured roots.
get_run_roots = resolve_run_roots


def register_run_path(path: PathLike, config_path: Optional[PathLike] = None) -> dict:
    """Persist an add-run directory in ``extra_runs`` and return the config."""
    config_file = _path_arg(config_path)
    candidate = _resolved_path(path, Path.cwd())
    with _CONFIG_LOCK:
        config = load_config(config_file)
        existing = list(config.get("extra_runs", []))
        stored = str(candidate)
        existing_paths = {
            str(_resolved_path(value, config_file.parent)) for value in existing
        }
        if stored not in existing_paths:
            existing.append(stored)
        config["extra_runs"] = existing
        return save_config(config, config_file)


# Names used by the add-run UI and by callers that prefer a verb.
register_run = register_run_path
add_run = register_run_path
add_run_path = register_run_path


__all__ = [
    "CONFIG_PATH", "load_config", "save_config", "resolve_run_root",
    "resolve_run_roots", "get_run_roots", "register_run_path", "register_run",
    "add_run", "add_run_path",
]
