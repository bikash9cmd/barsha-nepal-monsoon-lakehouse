"""Charts in docs/img, drawn from the gold tables of a local lake.

    python scripts/make_charts.py --lake lake
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from barsha.alerts import STATION_NAMES  # noqa: E402
from barsha.gold import load_gold  # noqa: E402
from barsha.storage import open_lake  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
ABSENT = "#f0efec"

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "xtick.color": INK_2,
    "ytick.color": INK_2, "text.color": INK, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
})


def completeness_heatmap(lake, out: Path) -> None:
    rain = load_gold(lake, "rain_daily")
    rain["year"] = rain["obs_date"].dt.year
    per = rain.groupby(["station_id", "year"])["prcp_quality"].apply(lambda q: (q == "complete").sum())
    days_in_year = pd.Series({y: 366 if y % 4 == 0 else 365 for y in range(1976, 2026)})
    days_in_year[2025] = 236  # the archive ends on 24 August 2025
    share = (per / per.index.get_level_values("year").map(days_in_year).values).unstack("year")
    share = share.reindex(columns=range(1976, 2026))
    order = rain.groupby("station_id")["obs_date"].min().sort_values().index
    share = share.loc[order]

    cmap = matplotlib.colors.ListedColormap(BLUE_RAMP)
    cmap.set_bad(ABSENT)
    norm = matplotlib.colors.BoundaryNorm(np.linspace(0, 1, len(BLUE_RAMP) + 1), cmap.N)
    fig, ax = plt.subplots(figsize=(11, 4.8))
    im = ax.imshow(np.ma.masked_invalid(share.values.astype(float)), aspect="auto", cmap=cmap, norm=norm,
                   interpolation="nearest")
    ax.set_yticks(range(len(share)), [STATION_NAMES[s][0] for s in share.index])
    years = list(share.columns)
    ax.set_xticks([i for i, y in enumerate(years) if y % 5 == 0], [y for y in years if y % 5 == 0])
    ax.set_xticks(np.arange(-0.5, len(years)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(share)), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=1.5)
    ax.tick_params(which="both", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cbar.set_ticks([0, 0.5, 1], labels=["0%", "50%", "100%"])
    cbar.outline.set_visible(False)
    ax.set_title("Share of each year's days with a complete rainfall reading (grey: no file at all)",
                 loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def flood_2024(lake, out: Path) -> None:
    rain = load_gold(lake, "rain_daily")
    ktm = rain[(rain.station_id == "44454099999") & rain.obs_date.between("2024-09-20", "2024-09-30")]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = ktm["obs_date"].dt.strftime("%d").to_numpy()
    y = ktm["prcp_mm"].fillna(0).to_numpy()
    ax.bar(x, y, width=0.6, color=BLUE, zorder=3)
    day = ktm[ktm.obs_date == "2024-09-28"].iloc[0]
    for value, label in [(day["p99_wet_mm"], "1-in-100 rainy days at this station"),
                         (day["prior_max_mm"], "previous record (10 July 1994)")]:
        ax.axhline(value, color=INK_2, linewidth=1, linestyle=(0, (4, 3)), zorder=2)
        ax.text(-0.4, value + 3, f"{label}: {value:.0f} mm", color=INK_2, fontsize=9)
    for xi, yi in zip(x, y, strict=True):
        if yi >= 50:
            ax.text(xi, yi + 3, f"{yi:.0f} mm", ha="center", color=INK, fontsize=9, fontweight="bold")
    ax.set_ylim(0, 230)
    ax.set_ylabel("rain in the GSOD day (mm)")
    ax.set_xlabel("September 2024")
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.tick_params(length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.set_title("Kathmandu airport, September 2024: the wettest day in 48 years of this record",
                 loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lake", default="lake")
    parser.add_argument("--out", default="docs/img")
    args = parser.parse_args()
    lake, out = open_lake(args.lake), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    completeness_heatmap(lake, out / "completeness.png")
    flood_2024(lake, out / "kathmandu_sept_2024.png")


if __name__ == "__main__":
    main()
