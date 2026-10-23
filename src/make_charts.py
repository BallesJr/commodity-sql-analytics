from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")  # render to files, no window

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

DATABASE = "data/commodities.duckdb"
OUT_DIR = Path("reports/figures")

# Fixed ticker order; each instrument keeps the same color in every chart
TICKERS = ["CL=F", "BZ=F", "NG=F", "GC=F", "HG=F", "ZW=F"]
COLORS = {
    "CL=F": "#2a78d6",  # blue
    "BZ=F": "#eb6834",  # orange
    "NG=F": "#1baf7a",  # aqua
    "GC=F": "#eda100",  # yellow
    "HG=F": "#e87ba4",  # magenta
    "ZW=F": "#008300",  # green
}

# Chart chrome: light surface, dark text, recessive grid and axes
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "font.size": 10,
    "text.color": INK,
    "axes.labelcolor": INK_2,
    "axes.titlecolor": INK,
    "axes.titlesize": 11,
    "axes.edgecolor": AXIS,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2,
    "legend.frameon": False,
})


def query(con, path):
    """Run a .sql file and return the result as a DataFrame."""
    df = con.sql(Path(path).read_text(encoding="utf-8")).df()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def format_year_axis(ax):
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def save(fig, name):
    path = OUT_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {path.as_posix()}")


def plot_normalized_prices(df, names):
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.axhline(100, color=AXIS, linewidth=1)

    ends = []
    for t in TICKERS:
        s = df[df["ticker"] == t]
        ax.plot(s["date"], s["norm_price"], color=COLORS[t], linewidth=1.3, label=names[t])
        ends.append((s["norm_price"].iloc[-1], t, s["date"].iloc[-1]))
        ax.plot(s["date"].iloc[-1], s["norm_price"].iloc[-1], "o", color=COLORS[t],
                markersize=5, markeredgecolor=SURFACE, markeredgewidth=1.5)

    # Direct labels at the end of each line, nudged apart so they never overlap
    y_min, y_max = ax.get_ylim()
    gap = (y_max - y_min) * 0.045
    ends.sort()
    label_y = []
    for value, _, _ in ends:
        label_y.append(max(value, label_y[-1] + gap) if label_y else value)
    x_label = df["date"].max() + pd.Timedelta(days=60)
    for (value, t, _), y in zip(ends, label_y):
        ax.annotate(f"{names[t]}  {value:.0f}", xy=(x_label, y), va="center",
                    color=INK_2, fontsize=9, annotation_clip=False)

    ax.set_title("Normalized futures prices, 2016-2025 (first close = 100)", loc="left")
    ax.set_ylabel("Index level")
    format_year_axis(ax)
    ax.legend(loc="upper left", ncol=3, fontsize=9)
    save(fig, "normalized_prices.png")


def plot_small_multiples(df, value_col, names, title, ylabel, filename, fill=False):
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.5), sharex=True, sharey=True)
    for ax, t in zip(axes.flat, TICKERS):
        s = df[df["ticker"] == t]
        ax.plot(s["date"], s[value_col], color=COLORS[t], linewidth=1.1)
        if fill:
            ax.fill_between(s["date"], s[value_col], 0, color=COLORS[t], alpha=0.18, linewidth=0)
        ax.set_title(names[t], loc="left")
        ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0, decimals=0))
        format_year_axis(ax)
    for ax in axes[:, 0]:
        ax.set_ylabel(ylabel)
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, color=INK)
    fig.tight_layout()
    save(fig, filename)


def plot_correlation_heatmap(df, names):
    # Build a symmetric 6x6 matrix with 1 on the diagonal
    idx = {t: i for i, t in enumerate(TICKERS)}
    m = np.eye(len(TICKERS))
    for row in df.itertuples():
        i, j = idx[row.ticker_a], idx[row.ticker_b]
        m[i, j] = m[j, i] = row.corr

    # Diverging scale: red (negative) - gray (zero) - blue (positive)
    cmap = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"])

    fig, ax = plt.subplots(figsize=(8, 6.8))
    mesh = ax.pcolormesh(m, cmap=cmap, vmin=-1, vmax=1, edgecolors=SURFACE, linewidth=2)
    for i in range(len(TICKERS)):
        for j in range(len(TICKERS)):
            v = m[i, j]
            ax.text(j + 0.5, i + 0.5, f"{v:.2f}", ha="center", va="center", fontsize=10,
                    color="white" if abs(v) >= 0.6 else INK)

    labels = [names[t] for t in TICKERS]
    ax.set_xticks(np.arange(len(TICKERS)) + 0.5, labels, rotation=30, ha="right")
    ax.set_yticks(np.arange(len(TICKERS)) + 0.5, labels)
    ax.invert_yaxis()
    ax.set_aspect("equal")
    ax.grid(False)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    cbar = fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.03)
    cbar.set_label("Correlation")
    cbar.outline.set_visible(False)
    ax.set_title("Correlation of daily log returns, 2016-2025", loc="left")
    save(fig, "correlation_heatmap.png")


OUT_DIR.mkdir(parents=True, exist_ok=True)

# Read-only: charts never modify the database
con = duckdb.connect(DATABASE, read_only=True)
names = dict(con.sql("SELECT ticker, name FROM instruments").fetchall())

plot_normalized_prices(query(con, "sql/charts/normalized_prices.sql"), names)
plot_small_multiples(query(con, "sql/charts/rolling_vol.sql"), "vol_21d", names,
                     "21-day rolling volatility (annualized)", "Volatility",
                     "rolling_vol.png")
plot_small_multiples(query(con, "sql/charts/drawdowns.sql"), "drawdown", names,
                     "Drawdown from running peak", "Drawdown",
                     "drawdowns.png", fill=True)
plot_correlation_heatmap(query(con, "sql/analysis/04_correlations.sql"), names)

con.close()
