"""JSON serialization helpers for the display dataclasses.

The data layer deliberately stays independent of FastAPI.  This module is the
small boundary that turns its frozen dataclasses and numpy values into ordinary
JSON-compatible Python values for API responses.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from ..emri.types import RunDetail


_DETAIL_EXCLUDED_FIELDS = frozenset({"result", "param_space"})


def _dataclass_value(value: Any) -> Any:
    """Convert a dataclass without traversing excluded live result objects."""
    if isinstance(value, RunDetail):
        # ``dataclasses.asdict`` deep-copies arbitrary field values.  Replace the
        # two deliberately non-serializable fields before calling it so a live
        # upstream sampler/result is never copied or traversed at this boundary.
        safe_value = replace(value, result=None, param_space=None)
        payload = asdict(safe_value)
        for name in _DETAIL_EXCLUDED_FIELDS:
            payload.pop(name, None)
        return payload
    return asdict(value)


def to_jsonable(value: Any) -> Any:
    """Recursively return values accepted by the standard JSON encoder.

    Dataclasses are first lowered with :func:`dataclasses.asdict`.  Numpy scalar
    values become native Python scalars, arrays and tuples become lists, and
    paths become strings.  The data layer's ``"unset"`` sentinel is already a
    plain string and therefore passes through unchanged.  ``None`` remains
    ``None`` so raw manifest nulls and optional fields retain JSON null
    semantics.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(_dataclass_value(value))
    if isinstance(value, np.ndarray):
        return to_jsonable(value.tolist())
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.complexfloating):
        return complex(value)
    if isinstance(value, np.generic):
        return to_jsonable(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if isinstance(value, Mapping):
        return {to_jsonable(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, set):
        return [to_jsonable(item) for item in value]
    return value


class NumpyJSONEncoder(json.JSONEncoder):
    """``json.JSONEncoder`` that understands numpy values and dataclasses."""

    def default(self, o: Any) -> Any:
        converted = to_jsonable(o)
        if converted is o:
            return super().default(o)
        return converted


# Short aliases make the helper convenient for callers that use either naming
# convention while keeping one implementation and one documented contract.
NumpyEncoder = NumpyJSONEncoder
serialize = to_jsonable


def serialize_run_summary(summary: Any) -> dict[str, Any]:
    """Return one JSON-compatible ``RunSummary`` payload."""
    return to_jsonable(summary)


def serialize_run_detail(detail: RunDetail) -> dict[str, Any]:
    """Return a detail payload with live ``result`` and ``param_space`` omitted."""
    payload = to_jsonable(detail)
    if not isinstance(payload, dict):  # pragma: no cover - defensive contract guard
        raise TypeError("run detail serialization did not produce an object")
    payload.pop("result", None)
    payload.pop("param_space", None)
    return payload


__all__ = [
    "NumpyJSONEncoder",
    "NumpyEncoder",
    "serialize",
    "serialize_run_detail",
    "serialize_run_summary",
    "to_jsonable",
]
