"""Pure plot-request builders; no plotting dependency is imported here."""
from __future__ import annotations

import numbers
from typing import Any, Optional, Tuple

import numpy as np

from .types import PlotRequest, PlotTheme


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise TypeError(f"{name} must be an integer")
    return int(value)


def _theme(value: str | PlotTheme) -> PlotTheme:
    try:
        return value if isinstance(value, PlotTheme) else PlotTheme(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("theme must be one of: default, dark, paper") from exc


def _detail_result(detail: Any) -> Any:
    result = getattr(detail, "result", None)
    if result is None:
        raise ValueError("plot request requires a loaded run result")
    return result


def _detail_space(detail: Any) -> Any:
    space = getattr(detail, "param_space", None)
    if space is None:
        space = getattr(detail, "space", None)
    return space


def corner_request(
    detail: Any,
    top_n: int = 10,
    title: Optional[str] = None,
    truth: bool = True,
    theme: str | PlotTheme = "default",
) -> PlotRequest:
    """Build the arguments for upstream ``corner_plot.plot_result``.

    ``plot_result`` accepts ``result, space, top_n, title, annotate``.  The
    accepted GUI's ``truth`` toggle is metadata because upstream's function
    has no truth parameter (its corner frame draws truth by default); the
    eventual PNG endpoint can post-process that frame.  ``theme`` is likewise
    a future matplotlib-rcParams hint and is not passed to upstream.
    """
    count = _integer(top_n, "top_n")
    if count < 1:
        raise ValueError("top_n must be positive")
    selected_theme = _theme(theme)
    truth_value = bool(truth)
    kwargs = {
        "result": _detail_result(detail),
        "space": _detail_space(detail),
        "top_n": count,
        "title": title,
        "annotate": True,
    }
    return PlotRequest(
        kind="corner",
        upstream="emrisearch.plotting.corner_plot.plot_result",
        kwargs=kwargs,
        theme=selected_theme,
        truth=truth_value,
        options={"truth": truth_value, "theme": selected_theme.value},
    )


def _vector(value: Any, name: str) -> Tuple[float, ...]:
    if value is None:
        raise ValueError(f"connection request requires {name}")
    try:
        array = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"connection {name} must be a numeric vector") from exc
    if not np.all(np.isfinite(array)):
        raise ValueError(f"connection {name} contains non-finite values")
    return tuple(float(item) for item in array)


def connection_request(
    detail: Any,
    n: int = 81,
    t_range: Tuple[float, float] = (-0.3, 1.3),
    ylabel: Optional[str] = None,
    progress: bool = False,
) -> PlotRequest:
    """Build the arguments for upstream ``connection.connection``.

    The upstream signature is ``connection(f, a, b, t_range, n, space,
    labels, ylabel, title, progress)``.  ``a`` and ``b`` are search-coordinate
    vectors and ``space`` performs the search-to-physical mapping at evaluation
    time.  A bound statistic is intentionally represented by ``None`` here:
    the future endpoint must bind it from the run's heavy stack if available.
    """
    count = _integer(n, "n")
    if count < 1:
        raise ValueError("n must be positive")
    try:
        bounds = tuple(float(value) for value in t_range)
    except (TypeError, ValueError) as exc:
        raise ValueError("t_range must contain two numbers") from exc
    if len(bounds) != 2 or not all(np.isfinite(bounds)) or not bounds[1] > bounds[0]:
        raise ValueError("t_range must be two finite values with hi > lo")

    space = _detail_space(detail)
    if space is None:
        raise ValueError("connection request requires a parameter space")
    try:
        injection = _vector(space.truth_search, "injection")
    except AttributeError as exc:
        raise ValueError("connection space has no truth_search coordinate") from exc
    best = getattr(getattr(detail, "best", None), "search_coordinates", None)
    if best is None:
        best = getattr(getattr(detail, "best", None), "search", None)
    recovered = _vector(best, "recovered point")
    if len(injection) != len(recovered):
        raise ValueError("injection and recovered points have different dimensions")

    kwargs = {
        "f": None,
        "a": injection,
        "b": recovered,
        "t_range": bounds,
        "n": count,
        "space": space,
        "labels": ("injection", "recovered"),
        "ylabel": "statistic" if ylabel is None else str(ylabel),
        "title": None,
        "progress": bool(progress),
    }
    return PlotRequest(
        kind="connection",
        upstream="emrisearch.plotting.connection.connection",
        kwargs=kwargs,
        # The connection builder has no theme argument in the accepted IA;
        # default is the neutral future-render hint.
        theme=PlotTheme.DEFAULT,
        truth=None,
        options={"progress": bool(progress)},
    )


__all__ = ["corner_request", "connection_request"]
