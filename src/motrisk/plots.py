"""The image in REPORT.md: the money saved at p_crit = 0.1, by test year and by group of defects.

The left panel is the model, Repeat and Most popular, pooled over every entry, for each test year
from 2020 to 2025. The right panel is the six groups that save the most and the six that save the
least in 2025, among those whose precision and recall are both read. Both read what
analysis/01_next_test.py wrote to data/processed/evaluate/, so the image shows no number that file
does not. Needs the `figures` extra. Run from the repository's root:

    python src/motrisk/plots.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

EVALUATE = Path("data/processed/evaluate")
OUT = Path("figures/money_saved.png")
P_CRIT = 0.1
YEAR = 2025

INK, INK_2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1", "#fcfcfb"
SERIES = {"model": "#2a78d6", "repeat": "#eb6834", "most_popular": "#1baf7a"}
NAMES = {"model": "Our model", "repeat": "Repeat", "most_popular": "Most popular"}

# The short names REPORT.md uses for the groups the image can show.
SHORT = {
    "Noise, emissions and leaks > Fluid leaks > Engine oil leaks": "Engine oil leaks",
    "Brakes > Rigid brake pipes": "Rigid brake pipes",
    "Tyres > Tread depth": "Tyre tread depth",
    "Motorcycle structure and attachments > Exhaust system": "Motorcycle exhaust",
    "Visibility > Condition of glass > Windscreen": "Windscreen",
    "Identification of the vehicle > Registration plates": "Registration plates",
    "Brakes > Mechanical brake components > Brake cables, rods, levers and linkages > Rod": (
        "Brake rods"
    ),
    "Brakes > ABS / EBS / ESC > Anti-lock braking system": "Anti-lock brakes",
    "Visibility > Wipers": "Wipers",
    "Visibility > Washers": "Washers",
    "Lamps, reflectors and electrical equipment > Electrical equipment > Horn": "Horn",
    "Noise, emissions and leaks > Exhaust emissions > Spark ignition > Non catalyst emissions": (
        "Non-catalyst emissions"
    ),
}


def by_year(ax: plt.Axes, scores: pd.DataFrame) -> None:
    """Draw the money saved of the model and both baselines, pooled, for each test year."""
    pooled = scores[(scores.p_crit == P_CRIT) & (scores.scope == "pooled")]
    for source in ["model", "repeat", "most_popular"]:
        rows = pooled[pooled.source == source].sort_values("test_year")
        saved = rows.saved * 100
        ax.plot(
            rows.test_year,
            saved,
            color=SERIES[source],
            lw=2,
            marker="o",
            ms=6,
            markeredgecolor=SURFACE,
            markeredgewidth=1.5,
            zorder=3,
        )
        ax.annotate(
            f"{NAMES[source]}  {saved.iloc[-1]:.1f}%",
            (rows.test_year.iloc[-1], saved.iloc[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=10,
        )
        ax.annotate(
            f"{saved.iloc[0]:.1f}%",
            (rows.test_year.iloc[0], saved.iloc[0]),
            xytext=(0, -16 if source == "most_popular" else 9),
            textcoords="offset points",
            ha="center",
            color=INK_2,
            fontsize=9,
        )
    ax.set_xlim(2019.6, 2027.0)
    ax.set_xticks(range(2020, 2026))
    ax.set_ylim(0, 15)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.spines["left"].set_visible(False)
    ax.set_title(
        "Every year, our model saves more than either rule", loc="left", fontsize=12, pad=12
    )
    ax.set_xlabel("Test year")


def by_group(ax: plt.Axes, groups: pd.DataFrame) -> None:
    """Draw the six groups that save the most and the six that save the least in YEAR."""
    read = groups[(groups.test_year == YEAR) & (groups.p_crit == P_CRIT)]
    read = read.dropna(subset=["precision", "recall"]).sort_values("saved", ascending=False)
    shown = [*read.head(6).itertuples(), *read.tail(6).itertuples()]
    # Twelve rows from the top, with a gap before the six that save the least.
    ys = [12 - i if i < 6 else 10.4 - i for i in range(12)]
    for y, row in zip(ys, shown, strict=True):
        saved = row.saved * 100
        ax.barh(y, saved, height=0.62, color=SERIES["model"], zorder=3)
        label = f"{saved:.1f}%".replace("-", "\u2212") if round(saved, 1) != 0 else "0.0%"
        ax.annotate(
            label,
            (max(saved, 0), y),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=INK_2,
        )
    ax.set_yticks(ys)
    ax.set_yticklabels([SHORT[row.group_path] for row in shown])
    ax.axvline(0, color=MUTED, lw=0.8, zorder=4)
    ax.set_xlim(-2, 40)
    ax.set_ylim(-1.3, 13.2)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.text(0, 12.75, "THE SIX THAT SAVE THE MOST", va="center", color=MUTED, fontsize=8.5)
    ax.text(0, 5.15, "THE SIX THAT SAVE THE LEAST", va="center", color=MUTED, fontsize=8.5)
    ax.set_title(f"Where it saves: defect groups, {YEAR}", loc="left", fontsize=12, pad=12)


def main() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "text.color": INK,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK_2,
            "axes.titlecolor": INK,
            "xtick.color": INK_2,
            "ytick.color": INK_2,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.major.size": 0,
            "ytick.major.size": 0,
        }
    )
    fig, (left, right) = plt.subplots(
        1, 2, figsize=(12.5, 5.2), gridspec_kw={"width_ratios": [1, 1.15]}
    )
    for item in (fig, left, right):
        item.set_facecolor(SURFACE)
    groups = pd.read_csv(EVALUATE / "groups.csv")
    by_year(left, pd.read_csv(EVALUATE / "scores.csv"))
    by_group(right, groups)
    year = groups[(groups.test_year == YEAR) & (groups.p_crit == P_CRIT)]
    unflagged = year[(year["flags"] == 0) & (year.problems >= 100)]
    share = unflagged.problems.sum() / year.problems.sum()
    fig.text(
        0.01,
        0.015,
        f"Groups: those with at least 100 problems and 100 flags in {YEAR}. "
        f"The {len(unflagged)} groups with 100 problems or more that the model never flags hold "
        f"{share:.1%} of the problems.",
        fontsize=8.5,
        color=INK_2,
        va="bottom",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1), w_pad=4)
    OUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUT, dpi=150, facecolor=SURFACE)
    print(OUT)


if __name__ == "__main__":
    main()
