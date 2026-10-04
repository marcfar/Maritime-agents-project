"""Dashboard: one image that summarises the cleaned data.

Reads data/clean.csv (produced by the data agent) and writes outputs/dashboard.png.
It uses no AI: it is plain pandas and matplotlib, so the picture can be checked
against the agents' brief.

Run:  python dashboard.py
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

from config import DATA_DIR, OUTPUT_DIR

TRAFFIC = "IS.SHP.GOOD.TU"
CONNECTIVITY = "IS.SHP.GCNW.XQ"

# Countries drawn as coloured lines. The colour belongs to the country and is the
# same in every panel. Keep this list to four: more colours stop being distinguishable.
FOCUS = {"SWE": "Sweden", "DNK": "Denmark", "NOR": "Norway", "FIN": "Finland"}
COLOURS = {"SWE": "#2a78d6", "DNK": "#eb6834", "NOR": "#1baf7a", "FIN": "#eda100"}

# Countries named on the scatter plot, besides the focus countries.
CALL_OUTS = {"CHN": "China", "USA": "United States", "SGP": "Singapore",
             "IDN": "Indonesia", "FRA": "France"}

# Where each name sits relative to its dot on the scatter plot: (x, y) in points and
# the text alignment. Countries not listed here get the default (to the right).
LABEL_PLACEMENT = {"DNK": ((-7, 4), "right"), "NOR": ((-7, -4), "right")}

SURFACE, INK, INK_2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, OTHER = "#e1e0d9", "#c3c2b7", "#b9b8b0"


def latest_common_year(df: pd.DataFrame) -> int:
    """Last year in which both indicators have data."""
    years = df.groupby("indicator")["year"].apply(set)
    return max(years[TRAFFIC] & years[CONNECTIVITY])


def short_number(value: float, _pos=None) -> str:
    """1500000 -> '1.5M', 20000 -> '20k'."""
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= limit:
            return f"{value / limit:g}{suffix}"
    return f"{value:g}"


def style(ax, title: str, subtitle: str) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, length=0, labelsize=9)
    ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold", pad=24)
    ax.text(0, 1.03, subtitle, transform=ax.transAxes, color=INK_2, fontsize=9.5)


def scatter_panel(ax, df: pd.DataFrame, year: int) -> None:
    wide = df[df["year"] == year].pivot(index="country_code", columns="indicator", values="value").dropna()
    rho = wide[TRAFFIC].rank().corr(wide[CONNECTIVITY].rank())
    names = {**FOCUS, **CALL_OUTS}
    named = wide[wide.index.isin(names)]
    rest = wide[~wide.index.isin(names)]

    ax.scatter(rest[TRAFFIC], rest[CONNECTIVITY], s=38, color=OTHER, edgecolor=SURFACE, linewidth=1)
    ax.scatter(named[TRAFFIC], named[CONNECTIVITY], s=52, color=INK, edgecolor=SURFACE, linewidth=1.5, zorder=3)
    for code, row in named.iterrows():
        offset, align = LABEL_PLACEMENT.get(code, ((7, 4), "left"))
        ax.annotate(names[code], (row[TRAFFIC], row[CONNECTIVITY]), xytext=offset,
                    textcoords="offset points", color=INK, fontsize=9, ha=align)

    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(short_number))
    ax.set_xlabel("Container port traffic, TEU (log scale)", color=INK_2, fontsize=9.5)
    ax.set_ylabel("Liner Shipping Connectivity Index", color=INK_2, fontsize=9.5)
    ax.set_ylim(bottom=0)
    style(ax, "Countries that move more containers are better connected",
          f"One dot per country, {year}. Spearman rank correlation {rho:.3f} across {len(wide)} countries.")


def lines_panel(ax, df: pd.DataFrame, indicator: str, title: str, subtitle: str) -> None:
    data = df[(df["indicator"] == indicator) & df["country_code"].isin(FOCUS)]
    ends = []
    for code, name in FOCUS.items():
        s = data[data["country_code"] == code].sort_values("year")
        if s.empty:
            continue
        ax.plot(s["year"], s["value"], color=COLOURS[code], linewidth=2, solid_capstyle="round", label=name)
        last = s.iloc[-1]
        ax.scatter(last["year"], last["value"], s=52, color=COLOURS[code], edgecolor=SURFACE, linewidth=1.5, zorder=3)
        ends.append((last["value"], last["year"], name))
    ax.set_ylim(bottom=0)

    # Name each line at its end. Names that would overlap are spread around their
    # common centre, so each name stays next to its own line.
    gap = 0.075 * ax.get_ylim()[1]
    clusters = []
    for value, year, name in sorted(ends):
        if clusters and value - clusters[-1][-1][0] < gap:
            clusters[-1].append((value, year, name))
        else:
            clusters.append([(value, year, name)])
    top = ax.get_ylim()[1]
    for cluster in clusters:
        centre = sum(value for value, _, _ in cluster) / len(cluster)
        for i, (_, year, name) in enumerate(cluster):
            label_y = centre + (i - (len(cluster) - 1) / 2) * gap
            top = max(top, label_y + gap / 2)
            ax.annotate(name, (year, label_y), xytext=(9, 0), textcoords="offset points",
                        color=INK_2, fontsize=9, va="center")
    ax.set_ylim(0, top)

    # Leave room on the right for the names, and put ticks only on years with data.
    first, last_year = int(data["year"].min()), int(data["year"].max())
    step = 1 if last_year - first <= 7 else 2
    ax.set_xticks(sorted(range(last_year, first - 1, -step)))
    ax.set_xlim(first - 0.3, last_year + 0.17 * (last_year - first))
    ax.yaxis.set_major_formatter(FuncFormatter(short_number))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{int(v)}"))
    style(ax, title, subtitle)


def build(df: pd.DataFrame):
    year = latest_common_year(df)
    plt.rcParams["font.family"] = "sans-serif"
    fig = plt.figure(figsize=(12, 10.2), facecolor=SURFACE)
    grid = fig.add_gridspec(2, 2, height_ratios=[1.25, 1], hspace=0.5, wspace=0.22,
                            left=0.07, right=0.97, top=0.9, bottom=0.11)

    scatter_panel(fig.add_subplot(grid[0, :]), df, year)

    traffic = df[df["indicator"] == TRAFFIC]
    connectivity = df[df["indicator"] == CONNECTIVITY]
    left = fig.add_subplot(grid[1, 0])
    right = fig.add_subplot(grid[1, 1])
    lines_panel(left, df, TRAFFIC, "Nordic container traffic",
                f"TEU per year, {traffic['year'].min()}–{traffic['year'].max()}")
    lines_panel(right, df, CONNECTIVITY, "Nordic liner connectivity",
                f"Index, {connectivity['year'].min()}–{connectivity['year'].max()}")

    handles, labels = left.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), frameon=False,
               fontsize=10, labelcolor=INK_2, bbox_to_anchor=(0.5, 0.035), handlelength=1.6)
    fig.suptitle("Container traffic and liner connectivity", x=0.07, y=0.975, ha="left",
                 color=INK, fontsize=16, fontweight="bold")
    fig.text(0.07, 0.012, "Source: World Bank Open Data (UNCTAD). Data cleaned by the data agent; "
             "figure drawn with pandas and matplotlib.", color=MUTED, fontsize=8.5)
    return fig


def main() -> None:
    df = pd.read_csv(DATA_DIR / "clean.csv")
    OUTPUT_DIR.mkdir(exist_ok=True)
    fig = build(df)
    path = OUTPUT_DIR / "dashboard.png"
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
