"""Matplotlib recipes shared by the server-side PNG renderers.

These values are intentionally kept in the data-layer namespace as a small,
additive contract for the API.  The renderer must not import prototype code at
runtime.
"""

# accepted theme recipes from prototype/make_figs.py, 2026-08-29
THEMES = {
    "default": {
        "rc": {
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
            "text.color": "#1c2026",
            "axes.labelcolor": "#1c2026",
            "xtick.color": "#5c626d",
            "ytick.color": "#5c626d",
            "grid.color": "#dde0e5",
            "axes.edgecolor": "#c6cbd3",
        },
        "accent": "#c23a4e",
        "truth": "#c23a4e",
        "secondary": "#3a6ea5",
        "grid": True,
    },
    "dark": {
        "rc": {
            "figure.facecolor": "#0b0d10",
            "axes.facecolor": "#0b0d10",
            "text.color": "#d7dae0",
            "axes.labelcolor": "#d7dae0",
            "xtick.color": "#8b919c",
            "ytick.color": "#8b919c",
            "grid.color": "#23272e",
            "axes.edgecolor": "#2e333c",
        },
        "accent": "#e05d6f",
        "truth": "#e05d6f",
        "secondary": "#5b9bd5",
        "grid": True,
    },
    "paper": {
        "rc": {
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
            "text.color": "#1c2026",
            "axes.labelcolor": "#1c2026",
            "xtick.color": "#5c626d",
            "ytick.color": "#5c626d",
            "grid.color": "#eef0f3",
            "axes.edgecolor": "#c6cbd3",
        },
        "accent": "#c23a4e",
        "truth": "#c23a4e",
        "secondary": "#3a6ea5",
        "grid": False,
    },
}

__all__ = ["THEMES"]
