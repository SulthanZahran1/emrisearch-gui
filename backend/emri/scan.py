"""Recursive discovery of manifest-backed and legacy run directories."""
from __future__ import annotations

import logging
import os
import traceback
from pathlib import Path

from .summary import MANIFEST_NAME, STATE_NAME, summarize_run
from .types import RunSummary

_LOG = logging.getLogger(__name__)
_LAST_WARNINGS: tuple[str, ...] = ()


def _publish_warnings(values: list[str]) -> None:
    global _LAST_WARNINGS
    _LAST_WARNINGS = tuple(values)
    # Function attributes keep the simple ``scan_run_root.warnings`` access
    # available without adding a second result wrapper to the required API.
    setattr(scan_run_root, "last_warnings", _LAST_WARNINGS)
    setattr(scan_run_root, "warnings", _LAST_WARNINGS)


def get_scan_warnings() -> tuple[str, ...]:
    """Return warnings from the most recent :func:`scan_run_root` call."""
    return _LAST_WARNINGS


# A second spelling is convenient for a backend response serializer.
last_scan_warnings = get_scan_warnings


def scan_run_root(root: os.PathLike | str) -> list[RunSummary]:
    """Walk ``root`` and summarize every discovered run.

    A directory is a candidate when it contains ``manifest.json`` or
    ``sampler_state.pkl``.  Broken manifests, permission errors, and malformed
    legacy files are recorded in ``scan_run_root.last_warnings`` (also exposed
    by :func:`get_scan_warnings`) and do not prevent other runs from loading.
    Results are sorted by absolute path.
    """
    warnings: list[str] = []
    root_path = Path(root).expanduser()
    try:
        root_path = root_path.resolve(strict=False)
    except OSError as exc:
        message = f"could not resolve scan root {root!s}: {exc}"
        warnings.append(message)
        _LOG.warning(message)
        _publish_warnings(warnings)
        return []

    if not root_path.exists() or not root_path.is_dir():
        message = f"scan root is not a readable directory: {root_path}"
        warnings.append(message)
        _LOG.warning(message)
        _publish_warnings(warnings)
        return []

    candidates: list[Path] = []

    def onerror(error: OSError) -> None:
        message = f"could not read directory during scan: {error}"
        warnings.append(message)
        _LOG.warning(message)

    try:
        for directory, _subdirs, files in os.walk(
            root_path, topdown=True, onerror=onerror, followlinks=False
        ):
            file_names = set(files)
            if MANIFEST_NAME in file_names or STATE_NAME in file_names:
                candidates.append(Path(directory))
    except OSError as exc:
        message = f"scan failed below {root_path}: {exc}"
        warnings.append(message)
        _LOG.warning(message)

    summaries: list[RunSummary] = []
    for directory in sorted(set(candidates), key=lambda item: str(item)):
        try:
            summary = summarize_run(directory, root=root_path)
        except Exception:
            # The exception text is useful to a future UI toast, while the
            # individual broken run remains safely omitted from the rail.
            detail = traceback.format_exc().splitlines()[-1]
            message = f"skipping broken run {directory}: {detail}"
            warnings.append(message)
            _LOG.warning(message)
            continue
        summaries.append(summary)
        warnings.extend(
            f"{directory}: {warning}" for warning in summary.warnings
        )

    summaries.sort(key=lambda item: item.path)
    _publish_warnings(warnings)
    return summaries


setattr(scan_run_root, "last_warnings", ())
setattr(scan_run_root, "warnings", ())


__all__ = ["scan_run_root", "get_scan_warnings", "last_scan_warnings"]
