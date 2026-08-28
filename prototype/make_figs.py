#!/usr/bin/env python3
"""Generate prototype corner + connection plots for emrisearch-gui.

Reads the same run data the prototype HTML embeds (kept in sync by hand for
the prototype; the real backend will call emrisearch's own plotting code).
"""
import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import corner

OUT = os.path.join(os.path.dirname(__file__), "figs")
os.makedirs(OUT, exist_ok=True)

ACCENT = "#c23a4e"   # crimson, matches the prototype accent
TRUTH = "#c23a4e"

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


def make_samples(cfg):
    rng = np.random.default_rng(cfg["seed"])
    n = cfg["n"]
    ndim = cfg["ndim"]
    # mixture: one tight mode near best + a diffuse tail (search secondaries)
    tight = rng.normal(cfg["best"], cfg["sigma"], size=(int(n * 0.8), ndim))
    tail = rng.normal(cfg["best"], [s * 6 for s in cfg["sigma"]], size=(n - int(n * 0.8), ndim))
    pts = np.vstack([tight, tail])
    # log-density: negative quadratic distance to best, plus noise
    z = (pts - cfg["best"]) / cfg["sigma"]
    ld = -0.5 * np.sum(z**2, axis=1) + rng.normal(0, 0.4, size=n)
    return pts, ld


def corner_plot(cfg):
    pts, ld = make_samples(cfg)
    top = np.argsort(ld)[-10:]
    fig = corner.corner(
        pts[top],
        labels=cfg["names"],
        color=ACCENT,
        hist_kwargs={"density": True},
        plot_datapoints=True,
        plot_density=False,
        fill_contours=False,
        show_titles=False,
        quiet=True,
    )
    # truth lines + star, matching upstream corner_frame(truth=True)
    ndim = cfg["ndim"]
    for i in range(ndim):
        ax = fig.axes[i * ndim + i]
        ax.axvline(cfg["truth"][i], color=TRUTH, lw=1.0, alpha=0.9)
        for j in range(i):
            ax = fig.axes[i * ndim + j]
            ax.axvline(cfg["truth"][j], color=TRUTH, lw=0.8, alpha=0.7)
            ax.axhline(cfg["truth"][i], color=TRUTH, lw=0.8, alpha=0.7)
            ax.plot(cfg["truth"][j], cfg["truth"][i], marker="*", color=TRUTH, ms=7)
    fig.savefig(os.path.join(OUT, f"{cfg['name']}_corner.png"), dpi=110, bbox_inches="tight")
    plt.close(fig)


def connection_plot(cfg):
    # statistic along the line from injection (truth) to recovered (best),
    # t in [-0.3, 1.3] like connection_line(); single-peaked profile.
    t = np.linspace(-0.3, 1.3, 81)
    peak = 0.55
    width = 0.12
    base = -23100.0 if "emri_c" in cfg["name"] else -31200.0
    vals = base + 900.0 * np.exp(-0.5 * ((t - peak) / width) ** 2) + 8.0 * np.sin(t * 3.0)
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    ax.plot(t, vals, color=ACCENT, lw=1.6)
    ax.axvline(0.0, color=TRUTH, lw=1.0, alpha=0.8)
    ax.axvline(1.0, color="#3a6ea5", lw=1.0, alpha=0.8)
    ax.set_xlabel("t along line (0 = injection, 1 = recovered)")
    ax.set_ylabel("statistic")
    ax.set_title("connection", fontsize=10)
    ax.grid(alpha=0.15, lw=0.5)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, f"{cfg['name']}_connection.png"), dpi=110)
    plt.close(fig)


def main():
    for name, cfg in RUNS.items():
        cfg["name"] = name
        corner_plot(cfg)
        connection_plot(cfg)
        print(f"wrote {name}_corner.png + {name}_connection.png")
    print("done")


if __name__ == "__main__":
    main()
