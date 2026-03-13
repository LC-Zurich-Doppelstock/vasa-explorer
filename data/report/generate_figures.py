#!/usr/bin/env python3
"""
Generate analysis figures (Panels A-F) from Vasaloppet results data.

Reads:  results_clean.csv
Writes: fig_a_regime_change.png
        fig_b_dnf_decomposition.png
        fig_c_conditions_hardness.png
        fig_d_medals_scatter.png
        fig_e_medals_timeseries.png
        fig_f_similarity_heatmap.png

Usage:
    python generate_figures.py [--input results_clean.csv] [--outdir .]
"""

import argparse
import os
import sys

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import gaussian_kde


# ---------------------------------------------------------------------------
# Shared style
# ---------------------------------------------------------------------------

STYLE = {
    "font.family": "serif",
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.spines.top": False,
    "axes.spines.right": False,
}

# Column width: 84mm ≈ 3.3in
COL_W = 3.3

ERA1_COLOR = "#2166ac"
ERA2_COLOR = "#b2182b"
YEARS_EXCL = {2021}  # COVID elite-only edition


# ---------------------------------------------------------------------------
# Data loading & derived metrics
# ---------------------------------------------------------------------------


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    years = sorted(
        y for y in df.Year.unique() if 2011 <= y <= 2026 and y not in YEARS_EXCL
    )
    return df[df.Year.isin(years)].copy(), years


def compute_metrics(d: pd.DataFrame, years: list) -> dict:
    """Return a dict keyed by year with all derived metrics."""
    cps = [
        "Smågan",
        "Mångsbodarna",
        "Risberg",
        "Evertsberg",
        "Oxberg",
        "Hökberg",
        "Eldris",
    ]
    out = {}

    for year in years:
        yd = d[d.Year == year]
        fin = yd[(yd.Status == "Finished") & (yd.Finish.notna())]
        winner = fin.Finish.min()
        tnorm = fin.Finish / winner

        # Starters = those with a Smågan time
        hs = yd[yd["Smågan"].notna()].copy()
        n_starters = len(hs)

        # Quartile boundaries on ALL starters
        q25_t = np.percentile(hs["Smågan"].values, 25)
        q75_t = np.percentile(hs["Smågan"].values, 75)
        q1 = hs[hs["Smågan"] <= q25_t]
        q4 = hs[hs["Smågan"] > q75_t]

        q1_dnf = 100 * (q1.Status == "Did Not Finish").sum() / len(q1)
        q4_dnf = 100 * (q4.Status == "Did Not Finish").sum() / len(q4)
        overall_dnf = 100 * (hs.Status == "Did Not Finish").sum() / n_starters

        n_medal = int((tnorm <= 1.5).sum())

        out[year] = {
            "winner": winner,
            "p10": np.percentile(tnorm, 10),
            "p25": np.percentile(tnorm, 25),
            "p50": np.percentile(tnorm, 50),
            "p75": np.percentile(tnorm, 75),
            "p90": np.percentile(tnorm, 90),
            "q1_dnf": q1_dnf,
            "q4_dnf": q4_dnf,
            "overall_dnf": overall_dnf,
            "n_medal": n_medal,
            "medal_pct": 100 * n_medal / n_starters,
            "n_starters": n_starters,
            "n_finishers": len(fin),
        }

    return out


def z_within_era(values: dict, years: list) -> pd.Series:
    """Standardise values within each era (pre/post COVID gap)."""
    s = pd.Series(values)
    e1 = s[[y for y in years if y <= 2020]]
    e2 = s[[y for y in years if y >= 2022]]
    z = pd.Series(index=years, dtype=float)
    for y in years:
        ref = e1 if y <= 2020 else e2
        z[y] = (s[y] - ref.mean()) / ref.std()
    return z


def composite_hardness(m: dict, years: list) -> pd.Series:
    """Compute the conditions-only composite hardness score."""
    z_w = z_within_era({y: m[y]["winner"] for y in years}, years)
    z_p25 = z_within_era({y: m[y]["p25"] for y in years}, years)
    z_p50 = z_within_era({y: m[y]["p50"] for y in years}, years)
    z_q1 = z_within_era({y: m[y]["q1_dnf"] for y in years}, years)
    return (z_w + z_p25 + z_p50 + z_q1) / 4


# ---------------------------------------------------------------------------
# Individual figure generators
# ---------------------------------------------------------------------------


def fig_a_regime_change(m: dict, years: list, outdir: str):
    """Panel A: t_norm percentile evolution showing the structural shift."""
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(COL_W, 2.8))

        era1 = [y for y in years if y <= 2020]
        era2 = [y for y in years if y >= 2022]

        pct_cfg = [
            (10, ERA1_COLOR, 1.0, "P10"),
            (25, "#67a9cf", 1.0, "P25"),
            (50, "#333333", 1.6, "P50"),
            (75, "#ef8a62", 1.0, "P75"),
            (90, ERA2_COLOR, 1.0, "P90"),
        ]

        for pct, color, lw, label in pct_cfg:
            vals = [m[y][f"p{pct}"] for y in years]
            ax.plot(
                years,
                vals,
                "o-",
                color=color,
                linewidth=lw,
                markersize=3,
                label=label,
            )

        # Era means for P50 and P90
        for pct, color in [(50, "#333333"), (90, ERA2_COLOR)]:
            e1_mean = np.mean([m[y][f"p{pct}"] for y in era1])
            e2_mean = np.mean([m[y][f"p{pct}"] for y in era2])
            ax.hlines(
                e1_mean,
                2011,
                2020,
                colors=color,
                linestyles=":",
                alpha=0.5,
                linewidth=1.2,
            )
            ax.hlines(
                e2_mean,
                2022,
                2026,
                colors=color,
                linestyles=":",
                alpha=0.5,
                linewidth=1.2,
            )

        ax.axvline(2020.5, color="gray", linestyle="--", alpha=0.35, linewidth=0.8)
        ax.axhline(1.5, color="#e7298a", linestyle="-", alpha=0.35, linewidth=1.0)
        ax.text(2026.4, 1.5, "Medal", fontsize=5.5, color="#e7298a", va="center")

        ax.set_ylabel("t_norm")
        ax.set_title(
            "Regime change: normalised time distribution", fontsize=8, fontweight="bold"
        )
        ax.legend(
            loc="upper left",
            ncol=5,
            framealpha=0.9,
            fontsize=5.5,
            handlelength=1.2,
            columnspacing=0.8,
        )
        ax.set_xticks(years)
        ax.set_xticklabels([str(y)[2:] for y in years], rotation=45, fontsize=6)
        ax.set_xlabel("Year")

        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "fig_a_regime_change.png"))
        plt.close(fig)


def fig_b_dnf_decomposition(m: dict, years: list, outdir: str):
    """Panel B: Q1 vs Q4 DNF rates + overall DNF line."""
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(COL_W, 2.6))

        x = np.array(years)
        ax.bar(
            x - 0.22,
            [m[y]["q1_dnf"] for y in years],
            0.38,
            label="Q1 (fastest) — conditions",
            color="#e7298a",
            alpha=0.85,
        )
        ax.bar(
            x + 0.22,
            [m[y]["q4_dnf"] for y in years],
            0.38,
            label="Q4 (slowest) — structural",
            color="#a6761d",
            alpha=0.85,
        )
        ax.plot(
            years,
            [m[y]["overall_dnf"] for y in years],
            "ko-",
            linewidth=1.2,
            markersize=3,
            label="Overall DNF",
            zorder=10,
        )

        ax.axvline(2020.5, color="gray", linestyle="--", alpha=0.35, linewidth=0.8)
        ax.set_ylabel("DNF rate (%)")
        ax.set_title(
            "DNF decomposition by speed quartile", fontsize=8, fontweight="bold"
        )
        ax.legend(loc="upper left", fontsize=5.5)
        ax.set_xticks(years)
        ax.set_xticklabels([str(y)[2:] for y in years], rotation=45, fontsize=6)
        ax.set_xlabel("Year")

        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "fig_b_dnf_decomposition.png"))
        plt.close(fig)


def fig_c_conditions_hardness(comp: pd.Series, years: list, outdir: str):
    """Panel C: composite hardness score bar chart."""
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(COL_W, 2.4))

        vals = [comp[y] for y in years]
        colors = [
            "#b2182b"
            if v > 0.5
            else "#ef8a62"
            if v > 0
            else "#67a9cf"
            if v > -0.5
            else "#2166ac"
            for v in vals
        ]
        ax.bar(years, vals, color=colors, width=0.65, edgecolor="black", linewidth=0.3)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.axvline(2020.5, color="gray", linestyle="--", alpha=0.35, linewidth=0.8)

        for y in years:
            v = comp[y]
            offset = 0.05 if v >= 0 else -0.05
            va = "bottom" if v >= 0 else "top"
            ax.text(
                y,
                v + offset,
                f"{v:+.2f}",
                ha="center",
                va=va,
                fontsize=5.5,
                fontweight="bold",
            )

        ax.set_ylabel("Hardness (z-score)")
        ax.set_title(
            "Conditions hardness (structural effects removed)",
            fontsize=8,
            fontweight="bold",
        )
        ax.set_xticks(years)
        ax.set_xticklabels([str(y)[2:] for y in years], rotation=45, fontsize=6)
        ax.set_xlabel("Year")

        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "fig_c_conditions_hardness.png"))
        plt.close(fig)


def fig_d_medals_scatter(m: dict, comp: pd.Series, years: list, outdir: str):
    """Panel D: scatter of conditions hardness vs medal % with per-era regression."""
    era1 = [y for y in years if y <= 2020]
    era2 = [y for y in years if y >= 2022]

    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(COL_W, 2.8))

        for y in era1:
            ax.plot(
                comp[y],
                m[y]["medal_pct"],
                "o",
                color=ERA1_COLOR,
                markersize=5,
                zorder=5,
            )
            ax.annotate(
                str(y)[2:],
                (comp[y], m[y]["medal_pct"]),
                textcoords="offset points",
                xytext=(3, 3),
                fontsize=5.5,
                color=ERA1_COLOR,
            )
        for y in era2:
            ax.plot(
                comp[y],
                m[y]["medal_pct"],
                "s",
                color=ERA2_COLOR,
                markersize=5,
                zorder=5,
            )
            ax.annotate(
                str(y)[2:],
                (comp[y], m[y]["medal_pct"]),
                textcoords="offset points",
                xytext=(3, 3),
                fontsize=5.5,
                color=ERA2_COLOR,
            )

        # Per-era regression lines
        for ey, color, label_prefix in [
            (era1, ERA1_COLOR, "Era 1"),
            (era2, ERA2_COLOR, "Era 2"),
        ]:
            h = np.array([comp[y] for y in ey])
            mv = np.array([m[y]["medal_pct"] for y in ey])
            sl, ic, r, p, _ = stats.linregress(h, mv)
            xf = np.linspace(h.min() - 0.2, h.max() + 0.2, 50)
            ax.plot(
                xf,
                sl * xf + ic,
                "--",
                color=color,
                alpha=0.5,
                linewidth=1.0,
                label=f"{label_prefix}: r={r:.2f}, p={p:.4f}",
            )

        ax.set_xlabel("Conditions hardness (z-score)")
        ax.set_ylabel("Medal skiers (% of starters)")
        ax.set_title(
            "Harder conditions \u2192 fewer medals", fontsize=8, fontweight="bold"
        )
        ax.legend(fontsize=5.5, loc="upper right")

        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "fig_d_medals_scatter.png"))
        plt.close(fig)


def fig_e_medals_timeseries(m: dict, years: list, outdir: str):
    """Panel E: medal yield over time with era averages."""
    era1 = [y for y in years if y <= 2020]
    era2 = [y for y in years if y >= 2022]

    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(COL_W, 2.4))

        vals = [m[y]["medal_pct"] for y in years]
        colors = [ERA1_COLOR if y <= 2020 else ERA2_COLOR for y in years]
        ax.bar(
            years,
            vals,
            color=colors,
            width=0.65,
            edgecolor="black",
            linewidth=0.3,
            alpha=0.85,
        )

        e1_avg = np.mean([m[y]["medal_pct"] for y in era1])
        e2_avg = np.mean([m[y]["medal_pct"] for y in era2])
        ax.hlines(
            e1_avg,
            2010.5,
            2020.5,
            colors=ERA1_COLOR,
            linestyles="--",
            linewidth=1.2,
            label=f"Era 1 avg: {e1_avg:.1f}%",
        )
        ax.hlines(
            e2_avg,
            2021.5,
            2026.5,
            colors=ERA2_COLOR,
            linestyles="--",
            linewidth=1.2,
            label=f"Era 2 avg: {e2_avg:.1f}%",
        )
        ax.axvline(2020.5, color="gray", linestyle="--", alpha=0.35, linewidth=0.8)

        for y in years:
            ax.text(
                y,
                m[y]["medal_pct"] + 0.4,
                f"{m[y]['medal_pct']:.0f}%",
                ha="center",
                fontsize=5,
                fontweight="bold",
            )

        ax.set_ylabel("Medal skiers (% of starters)")
        ax.set_title(
            "Medal yield: structural drop + conditions", fontsize=8, fontweight="bold"
        )
        ax.legend(fontsize=6, loc="upper right")
        ax.set_xticks(years)
        ax.set_xticklabels([str(y)[2:] for y in years], rotation=45, fontsize=6)
        ax.set_xlabel("Year")
        ax.set_ylim(0, 27)

        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "fig_e_medals_timeseries.png"))
        plt.close(fig)


def fig_f_similarity_heatmap(d: pd.DataFrame, years: list, outdir: str):
    """Panel F: upper-triangle heatmap of pairwise density overlap."""
    n = len(years)

    # Compute t_norm per year (finishers only)
    tnorms = {}
    for year in years:
        yd = d[d.Year == year]
        fin = yd[(yd.Status == "Finished") & (yd.Finish.notna())]
        winner = fin.Finish.min()
        tnorms[year] = (fin.Finish / winner).values

    # KDE on common grid
    x_grid = np.linspace(1.0, 6.0, 2000)
    kdes = {}
    for year in years:
        kde = gaussian_kde(tnorms[year], bw_method="scott")
        kdes[year] = kde(x_grid)

    # Pairwise overlap coefficient
    ovl = np.ones((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            overlap = np.trapezoid(np.minimum(kdes[years[i]], kdes[years[j]]), x_grid)
            ovl[i, j] = overlap
            ovl[j, i] = overlap

    # --- Render as image ---
    from matplotlib.colors import Normalize
    from matplotlib.cm import ScalarMappable

    off_diag = ovl[np.triu_indices(n, k=1)]
    vmin_val, vmax_val = 0.55, float(off_diag.max())

    cmap = plt.cm.RdYlBu
    norm = Normalize(vmin=vmin_val, vmax=vmax_val)

    # Build RGBA image: upper triangle = colormap, diagonal = black, lower = white
    rgba = np.ones((n, n, 4))  # start white
    for i in range(n):
        for j in range(n):
            if i == j:
                rgba[i, j] = [0, 0, 0, 1]  # black diagonal
            elif j > i:
                rgba[i, j] = cmap(norm(ovl[i, j]))  # upper triangle
            # lower triangle stays white

    # Era break index
    era_break = next(i for i, y in enumerate(years) if y >= 2022)

    # Draw era separation lines (2px black) into the image
    # Horizontal line just above era_break row
    # Vertical line just left of era_break col
    # We'll draw these on the figure instead for crispness

    heatmap_style = {**STYLE, "axes.grid": False}
    with plt.rc_context(heatmap_style):
        fig, ax = plt.subplots(figsize=(COL_W, COL_W))

        ax.imshow(rgba, interpolation="nearest", aspect="equal")

        # Era separation lines
        eb = era_break - 0.5
        ax.plot([eb, eb], [-0.5, n - 0.5], color="black", linewidth=1.5)
        ax.plot([-0.5, n - 0.5], [eb, eb], color="black", linewidth=1.5)

        # Year labels along top and right
        for i, y in enumerate(years):
            lbl = f"'{str(y)[2:]}"
            # top labels
            ax.text(
                i,
                -0.7,
                lbl,
                ha="center",
                va="bottom",
                fontsize=6,
                rotation=45,
            )
            # right labels
            ax.text(
                n - 0.3,
                i,
                lbl,
                ha="left",
                va="center",
                fontsize=6,
            )

        # Era labels on the left
        e1_mid = (era_break - 1) / 2
        e2_mid = (era_break + n - 1) / 2
        ax.text(
            -1.0,
            e1_mid,
            "Era 1 (2011\u201320)",
            ha="center",
            va="center",
            fontsize=6,
            fontstyle="italic",
            color=ERA1_COLOR,
            rotation=90,
        )
        ax.text(
            -1.0,
            e2_mid,
            "Era 2 (22\u201326)",
            ha="center",
            va="center",
            fontsize=6,
            fontstyle="italic",
            color=ERA2_COLOR,
            rotation=90,
        )

        # Strip everything axis-related
        ax.axis("off")
        ax.set_xlim(-1.5, n + 0.8)
        ax.set_ylim(n + 0.8, -2.0)

        ax.set_title(
            "Distribution similarity (density overlap)",
            fontsize=8,
            fontweight="bold",
            pad=14,
        )

        # Colorbar at the bottom
        sm = ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = fig.colorbar(
            sm,
            ax=ax,
            shrink=0.7,
            pad=0.04,
            aspect=25,
            location="bottom",
        )
        cbar.set_label("Overlap coefficient", fontsize=7)
        cbar.ax.tick_params(labelsize=6)

        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "fig_f_similarity_heatmap.png"))
        plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Generate Vasaloppet analysis figures."
    )
    parser.add_argument(
        "--input", default="results_clean.csv", help="Path to results_clean.csv"
    )
    parser.add_argument("--outdir", default=".", help="Directory to write figure PNGs")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    os.makedirs(args.outdir, exist_ok=True)

    print(f"Loading data from {args.input} ...")
    d, years = load_data(args.input)
    print(f"  {len(d)} rows, years: {years[0]}-{years[-1]} ({len(years)} editions)")

    print("Computing metrics ...")
    m = compute_metrics(d, years)
    comp = composite_hardness(m, years)

    print("Generating figures ...")
    fig_a_regime_change(m, years, args.outdir)
    print("  fig_a_regime_change.png")

    fig_b_dnf_decomposition(m, years, args.outdir)
    print("  fig_b_dnf_decomposition.png")

    fig_c_conditions_hardness(comp, years, args.outdir)
    print("  fig_c_conditions_hardness.png")

    fig_d_medals_scatter(m, comp, years, args.outdir)
    print("  fig_d_medals_scatter.png")

    fig_e_medals_timeseries(m, years, args.outdir)
    print("  fig_e_medals_timeseries.png")

    fig_f_similarity_heatmap(d, years, args.outdir)
    print("  fig_f_similarity_heatmap.png")

    print("Done.")


if __name__ == "__main__":
    main()
