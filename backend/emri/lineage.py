"""Lineage-chain resolution from ``seeding.from_run`` pointers."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence

from .types import RunSummary


def _resolved(value: object) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        return str(Path(str(value)).expanduser().resolve(strict=False))
    except (OSError, ValueError):
        return None


def _basename(value: object) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).rstrip("/\\")
    return Path(text).name or None


def _indexes(summaries: Sequence[RunSummary]):
    by_id: dict[str, RunSummary] = {}
    by_path: dict[str, RunSummary] = {}
    by_basename: dict[str, RunSummary] = {}
    for summary in summaries:
        by_id.setdefault(summary.id, summary)
        for value in (summary.path, summary.out):
            key = _resolved(value)
            if key:
                by_path.setdefault(key, summary)
        for value in (summary.id, summary.path, summary.out):
            key = _basename(value)
            if key:
                by_basename.setdefault(key, summary)
    return by_id, by_path, by_basename


def _lookup(
    pointer: object,
    child: Optional[RunSummary],
    by_id: dict[str, RunSummary],
    by_path: dict[str, RunSummary],
    by_basename: dict[str, RunSummary],
) -> Optional[RunSummary]:
    if pointer in (None, ""):
        return None
    text = str(pointer).rstrip("/\\")
    if text in by_id:
        return by_id[text]
    absolute = _resolved(text)
    if absolute and absolute in by_path:
        return by_path[absolute]
    if child is not None and child.path:
        try:
            relative = Path(child.path).expanduser().resolve(strict=False).parent / text
            match = by_path.get(str(relative.resolve(strict=False)))
            if match is not None:
                return match
        except (OSError, ValueError):
            pass
    base = _basename(text)
    return by_basename.get(base) if base else None


def chain_of(
    run_summaries: Iterable[RunSummary],
    start_id: str,
) -> list[RunSummary]:
    """Return ancestors oldest-first, followed by all forward descendants.

    Pointers are accepted as absolute paths, relative paths, basenames, or
    already-relative summary ids.  Every traversal has a visited set, so a
    malformed/cyclic lineage cannot hang the backend.  Siblings that merely
    share a parent are not considered descendants, matching the accepted
    prototype's lineage strip.
    """
    summaries = list(run_summaries)
    by_id, by_path, by_basename = _indexes(summaries)
    start = _lookup(start_id, None, by_id, by_path, by_basename)
    if start is None:
        return []

    def parent(summary: RunSummary) -> Optional[RunSummary]:
        return _lookup(summary.from_run, summary, by_id, by_path, by_basename)

    # Walk backward from the selected run, then reverse so the oldest known
    # ancestor is rendered first.
    backward: list[RunSummary] = []
    visited: set[str] = set()
    current: Optional[RunSummary] = start
    while current is not None and current.id not in visited:
        visited.add(current.id)
        backward.append(current)
        current = parent(current)
    ancestors = list(reversed(backward))

    descendants: list[RunSummary] = []
    seen_descendants: set[str] = {item.id for item in ancestors}
    for candidate in summaries:
        if candidate.id == start.id or candidate.id in seen_descendants:
            continue
        current = candidate
        visited_candidate: set[str] = set()
        is_descendant = False
        while current is not None and current.id not in visited_candidate:
            visited_candidate.add(current.id)
            current = parent(current)
            if current is not None and current.id == start.id:
                is_descendant = True
                break
        if is_descendant:
            descendants.append(candidate)
            seen_descendants.add(candidate.id)

    return ancestors + descendants


__all__ = ["chain_of"]
