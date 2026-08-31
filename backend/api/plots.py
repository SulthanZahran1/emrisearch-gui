"""PNG renderers for the server-side plot endpoints."""
from __future__ import annotations

from dataclasses import fields
from io import BytesIO
from typing import Any, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from backend.emri.plot_themes import THEMES


CONNECTION_UNAVAILABLE_MESSAGE = (
    "connection plot unavailable — bound statistic stack not installed"
)


def _theme_name(value: Any) -> str:
    name = getattr(value, "value", value)
    name = str(name)
    if name not in THEMES:
        raise ValueError("theme must be one of: default, dark, paper")
    return name


def _figure_png(fig: Any, *, tight: bool = True) -> bytes:
    """Encode and close a Matplotlib figure."""
    output = BytesIO()
    try:
        save_kwargs = {"format": "png", "dpi": 110}
        if tight:
            save_kwargs["bbox_inches"] = "tight"
        fig.savefig(output, **save_kwargs)
        return output.getvalue()
    finally:
        plt.close(fig)
        output.close()


def _corner_title(result: Any, top_n: int, title: Any) -> Any:
    if title is not None:
        return title
    manifest = getattr(result, "manifest", None) or {}
    statistic = manifest.get("statistic", {}) if isinstance(manifest, Mapping) else {}
    statistic = statistic if isinstance(statistic, Mapping) else {}
    kind = statistic.get("kind", "?")
    nseg = f", N_seg={statistic['N_seg']}" if "N_seg" in statistic else ""
    try:
        count = len(result.finite().top(top_n).samples)
    except Exception:
        count = top_n
    return f"top {count} search points  ({kind}{nseg})"


def _compat_corner_frame(space: Any, title: Any, truth: bool) -> Any:
    """Use the upstream frame recipe with a corner-version-safe scaffold.

    The bundled upstream ``corner_frame`` uses two repeated truth rows.  Corner
    2.3 rejects a scaffold with fewer rows than dimensions, so the API keeps the
    same empty-frame recipe but supplies ``ndim + 1`` identical hidden rows.
    The hidden rows are clipped into the search box: corner's range validation
    rejects scaffold values outside the locked ranges, which would otherwise
    rupture the frame whenever the recorded truth sits outside the search box
    (mis-specified fixture or boundary-hugging real truth).
    """
    import corner
    from emrisearch.plotting.corner_plot import lock_axes

    ndim = int(space.ndim)
    boxes = np.asarray(list(space.box), dtype=float).reshape(ndim, 2)
    centers = (boxes[:, 0] + boxes[:, 1]) / 2.0
    raw = np.asarray(space.truth_search, dtype=float)
    seed = np.where(np.isnan(raw), centers, raw)
    seed = np.clip(seed, boxes[:, 0], boxes[:, 1])
    scaffold = np.repeat(np.atleast_2d(seed), max(ndim + 1, 2), axis=0)
    fig = corner.corner(
        scaffold,
        labels=list(space.labels),
        range=list(space.box),
        plot_datapoints=False,
        plot_density=False,
        plot_contours=False,
        hist_kwargs=dict(alpha=0, lw=0),
    )
    lock_axes(fig, space)
    if truth:
        corner.overplot_lines(fig, space.truth_search, color="crimson", lw=1.0, alpha=0.8)
        corner.overplot_points(
            fig,
            np.atleast_2d(space.truth_search),
            marker="*",
            color="crimson",
            markersize=11,
            linestyle="none",
        )
    if title:
        fig.suptitle(title, fontsize=10)
    return fig


def _corner_without_truth(
    result: Any,
    space: Any,
    top_n: int,
    title: Any,
    annotate: bool,
) -> Any:
    """Mirror upstream ``plot_result`` while suppressing its truth frame."""
    from emrisearch.plotting.corner_plot import corner_frame, overplot

    best = result.finite().top(top_n)
    title = _corner_title(result, top_n, title)
    try:
        fig = corner_frame(space, title=title, truth=False)
    except (AssertionError, ValueError):
        # See _compat_corner_frame: this is only a scaffold-size compatibility
        # fallback for corner 2.3, not an alternate plotting recipe. It also
        # clips out-of-box truth so the frame cannot be torn.
        fig = _compat_corner_frame(space, title=title, truth=False)
    labels = [f"{value:.4g}" for value in best.log_densities] if annotate else None
    overplot(fig, space, best.samples, labels=labels)
    return fig


def _corner_result_compat(
    result: Any,
    space: Any,
    top_n: int,
    title: Any,
    annotate: bool,
    truth: bool,
) -> Any:
    """Fallback mirror of upstream ``plot_result`` for corner 2.3."""
    from emrisearch.plotting import corner_plot

    best = result.finite().top(top_n)
    fig = _compat_corner_frame(space, _corner_title(result, top_n, title), truth=truth)
    labels = [f"{value:.4g}" for value in best.log_densities] if annotate else None
    corner_plot.overplot(fig, space, best.samples, labels=labels)
    return fig


def corner_png(detail: Any, request: Any) -> bytes:
    """Render a corner plot request to PNG bytes.

    ``truth=True`` deliberately calls upstream ``plot_result``.  Since that
    function always creates its frame with truth lines, the false branch uses
    the same ``corner_frame``/``overplot`` recipe with ``truth=False``.
    """
    from emrisearch.plotting import corner_plot

    kwargs = dict(getattr(request, "kwargs", {}))
    result = kwargs.get("result", getattr(detail, "result", None))
    space = kwargs.get("space", getattr(detail, "param_space", None))
    top_n = int(kwargs.get("top_n", 10))
    title = kwargs.get("title")
    annotate = bool(kwargs.get("annotate", True))
    truth = bool(getattr(request, "truth", True))
    theme_name = _theme_name(getattr(request, "theme", "default"))
    theme = THEMES[theme_name]

    with plt.rc_context(theme["rc"]):
        if truth:
            try:
                fig = corner_plot.plot_result(
                    result=result,
                    space=space,
                    top_n=top_n,
                    title=title,
                    annotate=annotate,
                )
            except (AssertionError, ValueError):
                # The accepted upstream recipe is retained; corner 2.3 needs a
                # larger hidden scaffold than the upstream helper supplies, and
                # out-of-box truth must not tear the frame (the compat scaffold
                # is clipped into the search box).
                fig = _corner_result_compat(
                    result, space, top_n, title, annotate, truth=True
                )
        else:
            fig = _corner_without_truth(result, space, top_n, title, annotate)
        return _figure_png(fig)


def _filtered_dataclass_kwargs(cls: Any, values: Mapping[str, Any]) -> dict[str, Any]:
    names = {field.name for field in fields(cls)}
    return {name: value for name, value in values.items() if name in names}


def _bind_bound_statistic(detail: Any) -> tuple[Any, Any]:
    """Reconstruct a real upstream run and bind its statistic.

    Constructing the run is intentionally best effort.  In a light install the
    lazy dataset reaches the missing waveform/statistic dependencies only when
    the connection line is evaluated; the caller detects that failure and
    falls back to the explicit placeholder rather than emitting fake values.
    """
    from emrisearch.config import ModeConfig, NoiseConfig, ObsConfig
    from emrisearch.params import ParamSpace, SourceParams
    from emrisearch.run import ParisRun
    from emrisearch.statistic import Statistic

    manifest = getattr(detail, "manifest", None)
    if not isinstance(manifest, Mapping):
        raise ValueError("run has no manifest for bound-statistic reconstruction")

    source_values = manifest.get("source")
    if not isinstance(source_values, Mapping):
        raise ValueError("manifest has no source mapping")
    source = SourceParams(**_filtered_dataclass_kwargs(SourceParams, source_values))

    obs_values = manifest.get("obs")
    if not isinstance(obs_values, Mapping):
        raise ValueError("manifest has no observation mapping")
    obs = ObsConfig(**_filtered_dataclass_kwargs(ObsConfig, obs_values))

    noise_values = manifest.get("noise", {})
    noise = NoiseConfig(**_filtered_dataclass_kwargs(NoiseConfig, noise_values))
    mode_values = manifest.get("modes", {})
    modes = ModeConfig(**_filtered_dataclass_kwargs(ModeConfig, mode_values))

    statistic_values = manifest.get("statistic")
    if not isinstance(statistic_values, Mapping):
        raise ValueError("manifest has no statistic mapping")
    statistic = Statistic.from_manifest(dict(statistic_values))

    space_values = manifest.get("space")
    if not isinstance(space_values, Mapping):
        raise ValueError("manifest has no search-space mapping")
    space = ParamSpace.from_manifest(dict(space_values))
    run = ParisRun(
        source=source,
        obs=obs,
        space=space,
        out=str(getattr(detail, "path", manifest.get("out", "."))),
        statistic=statistic,
        noise=noise,
        modes=modes,
    )
    return run.statistic.bind(run.data), run.space


def _connection_kwargs(request: Any, bound: Any, space: Any) -> dict[str, Any]:
    kwargs = dict(getattr(request, "kwargs", {}))
    kwargs["f"] = bound
    kwargs["space"] = space
    return kwargs


def connection_png(detail: Any, request: Any) -> bytes:
    """Render a connection plot, or a truthful themed unavailable placeholder."""
    theme_name = _theme_name(getattr(request, "theme", "default"))
    theme = THEMES[theme_name]
    fig = None
    try:
        # Keep even the plotting import inside the best-effort boundary: an
        # optional dependency may fail while importing the upstream module.
        from emrisearch.plotting import connection as upstream_connection

        bound, space = _bind_bound_statistic(detail)
        kwargs = _connection_kwargs(request, bound, space)
        with plt.rc_context(theme["rc"]):
            plotted = upstream_connection(**kwargs)
            if not isinstance(plotted, tuple) or len(plotted) < 3:
                raise RuntimeError("upstream connection returned no values")
            ax, _t_values, values = plotted[0], plotted[1], plotted[2]
            fig = getattr(ax, "figure", None)
            values = np.asarray(values, dtype=float).reshape(-1)
            # Upstream intentionally converts per-point evaluation failures to
            # NaN.  Treat an incomplete curve as a failed real path too; this is
            # what makes a missing heavy stack visibly degrade instead of
            # producing an empty, misleading chart.
            if values.size == 0 or not np.all(np.isfinite(values)):
                raise RuntimeError("bound statistic evaluation returned non-finite values")
            if fig is None:
                raise RuntimeError("upstream connection returned no figure")
            return _figure_png(fig)
    except Exception:
        if fig is not None:
            plt.close(fig)
        return placeholder_png(theme_name, CONNECTION_UNAVAILABLE_MESSAGE)


def placeholder_png(theme: Any, message: str) -> bytes:
    """Render a themed, labeled placeholder without fabricating a data curve."""
    theme_name = _theme_name(theme)
    recipe = THEMES[theme_name]
    with plt.rc_context(recipe["rc"]):
        fig, ax = plt.subplots(figsize=(5.2, 3.4))
        # Match the accepted prototype's connection-figure grid semantics
        # (prototype/make_figs.py connection_plot: grid on for default/dark,
        # off for paper) so the placeholder is theme-distinct exactly like the
        # real figure would be.
        if recipe["grid"]:
            ax.grid(alpha=0.15, lw=0.5)
        else:
            ax.grid(False)
        # Gridlines draw at tick positions; give the placeholder a few ticks so
        # the default/dark grid is actually visible (and paper stays gridless).
        ax.set_xticks([0.2, 0.5, 0.8])
        ax.set_yticks([0.2, 0.5, 0.8])
        ax.tick_params(length=0, labelleft=False, labelbottom=False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.text(
            0.5,
            0.56,
            message,
            ha="center",
            va="center",
            color=recipe["accent"],
            family="monospace",
            fontsize=10,
            wrap=True,
            transform=ax.transAxes,
        )
        ax.text(
            0.5,
            0.38,
            "no statistic curve rendered",
            ha="center",
            va="center",
            color=recipe["secondary"],
            family="monospace",
            fontsize=9,
            transform=ax.transAxes,
        )
        return _figure_png(fig)


__all__ = [
    "CONNECTION_UNAVAILABLE_MESSAGE",
    "connection_png",
    "corner_png",
    "placeholder_png",
]
