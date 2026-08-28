#!/usr/bin/env python3
"""Generate themed plot variants for the emrisearch-gui prototype.

Variant matrix (every combination is pre-rendered so config always matches output):
  corner:     3 themes x top_n {10,20,50,100} x annotate {0,1} x truth {0,1}
  connection: 3 themes x n {41,81,161} x t_range {(-0.3,1.3),(-0.5,1.5),(0.0,1.0)}

The prototype swaps between these PNGs as the user drags sliders. The real
backend renders any value with emrisearch's own plotting code.
"""
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import corner

OUT = os.path.join(os.path.dirname(__file__), "figs")
os.makedirs(OUT, exist_ok=True)

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

RUNS = {
    "emri_c_lhs_s12": {
        "ndim": 5,
        "names": ["log10 m1", "log10 m2", "a", "p0", "e0"],
        "truth": [5.477, 1.0, 0.3, 12.0, 0.2],
        "best": [5.31, 1.14, 0.41, 13.2, 0.31],
        "sigma": [0.18, 0.12, 0.09, 0.35, 0.07],
        "n": 2000,
        "seed": 1,
    },
    "emri_c_merge_s12": {
        "ndim": 5,
        "names": ["log10 m1", "log10 m2", "a", "p0", "e0"],
        "truth": [5.477, 1.0, 0.3, 12.0, 0.2],
        "best": [5.44, 1.03, 0.33, 12.3, 0.22],
        "sigma": [0.05, 0.04, 0.03, 0.12, 0.02],
        "n": 12500,
        "seed": 2,
    },
    "emri_c_anneal_s12": {
        "ndim": 5,
        "names": ["log10 m1", "log10 m2", "a", "p0", "e0"],
        "truth": [5.477, 1.0, 0.3, 12.0, 0.2],
        "best": [5.46, 1.01, 0.31, 12.1, 0.21],
        "sigma": [0.02, 0.015, 0.012, 0.05, 0.008],
        "n": 25000,
        "seed": 3,
    },
    "emri_g_merge_7d": {
        "ndim": 7,
        "names": ["log10 m1", "log10 m2", "a", "p0", "e0", "qS", "phiS"],
        "truth": [5.903, 1.079, 0.5, 11.0, 0.15, 0.352, 3.0],
        "best": [5.62, 1.08, 0.44, 11.8, 0.19, 0.42, 2.9],
        "sigma": [0.2, 0.1, 0.08, 0.3, 0.05, 0.08, 0.2],
        "n": 12000,
        "seed": 4,
    },
}

CORNER_TOP_N = [10, 20, 50, 100]
CONN_N = [41, 81, 161]
CONN_T_RANGE = [(-0.3, 1.3), (-0.5, 1.5), (0.0, 1.0)]


def make_samples(cfg):
    rng = np.random.default_rng(cfg["seed"])
    n = cfg["n"]
    ndim = cfg["ndim"]
    tight = rng.normal(cfg["best"], cfg["sigma"], size=(int(n * 0.8), ndim))
    tail = rng.normal(cfg["best"], [s * 6 for s in cfg["sigma"]], size=(n - int(n * 0.8), ndim))
    pts = np.vstack([tight, tail])
    z = (pts - cfg["best"]) / cfg["sigma"]
    ld = -0.5 * np.sum(z**2, axis=1) + rng.normal(0, 0.4, size=n)
    return pts, ld


def corner_plot(cfg, theme_name, top_n, annotate, truth):
    theme = THEMES[theme_name]
    with plt.rc_context(theme["rc"]):
        pts, ld = make_samples(cfg)
        top = np.argsort(ld)[-top_n:]
        labels = [f"{v:.4g}" for v in ld[top]] if annotate else None
        fig = corner.corner(
            pts[top],
            labels=cfg["names"],
            color=theme["accent"],
            hist_kwargs={"density": True},
            plot_datapoints=True,
            plot_density=False,
            fill_contours=False,
            show_titles=False,
            quiet=True,
        )
        fig.suptitle(f"top {top_n} search points  (f_max)", fontsize=10)
        ndim = cfg["ndim"]
        if truth:
            for i in range(ndim):
                ax = fig.axes[i * ndim + i]
                ax.axvline(cfg["truth"][i], color=theme["truth"], lw=1.0, alpha=0.9)
                for j in range(i):
                    ax = fig.axes[i * ndim + j]
                    ax.axvline(cfg["truth"][j], color=theme["truth"], lw=0.8, alpha=0.7)
                    ax.axhline(cfg["truth"][i], color=theme["truth"], lw=0.8, alpha=0.7)
                    ax.plot(cfg["truth"][j], cfg["truth"][i], marker="*", color=theme["truth"], ms=7)
        fig.savefig(
            os.path.join(OUT, f"{cfg['name']}_corner_{theme_name}_top{top_n}_a{int(annotate)}_t{int(truth)}.png"),
            dpi=110, bbox_inches="tight",
        )
        plt.close(fig)


def connection_plot(cfg, theme_name, n, t_range):
    theme = THEMES[theme_name]
    with plt.rc_context(theme["rc"]):
        t = np.linspace(t_range[0], t_range[1], n)
        peak, width = 0.55, 0.12
        base = -23100.0 if "emri_c" in cfg["name"] else -31200.0
        vals = base + 900.0 * np.exp(-0.5 * ((t - peak) / width) ** 2) + 8.0 * np.sin(t * 3.0)
        fig, ax = plt.subplots(figsize=(5.2, 3.4))
        ax.plot(t, vals, color=theme["accent"], lw=1.6)
        ax.axvline(0.0, color=theme["truth"], lw=1.0, alpha=0.8)
        ax.axvline(1.0, color=theme["secondary"], lw=1.0, alpha=0.8)
        ax.set_xlabel("t along line (0 = injection, 1 = recovered)")
        ax.set_ylabel("statistic")
        ax.set_title("connection", fontsize=10)
        if theme["grid"]:
            ax.grid(alpha=0.15, lw=0.5)
        else:
            ax.grid(False)
        fig.tight_layout()
        t0 = int(round(t_range[0] * 10))
        t1 = int(round(t_range[1] * 10))
        fig.savefig(
            os.path.join(OUT, f"{cfg['name']}_connection_{theme_name}_n{n}_t{t0}_{t1}.png"),
            dpi=110,
        )
        plt.close(fig)


def main():
    total = 0
    for name, cfg in RUNS.items():
        cfg["name"] = name
        for theme in THEMES:
            for top_n in CORNER_TOP_N:
                for annotate in (False, True):
                    for truth in (False, True):
                        corner_plot(cfg, theme, top_n, annotate, truth)
                        total += 1
            for n in CONN_N:
                for t_range in CONN_T_RANGE:
                    connection_plot(cfg, theme, n, t_range)
                    total += 1
        print(f"{name}: done")
    print(f"wrote {total} figures")


if __name__ == "__main__":
    main()
