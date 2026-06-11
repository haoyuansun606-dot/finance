"""Yearly return heatmaps."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.metrics import performance_summary, yearly_returns
from src.viz.style import configure_chinese_matplotlib


def plot_yearly_heatmap(
    nav: pd.Series,
    strategy_label: str,
    version_title: str,
    out_path: Path,
) -> None:
    """One-row heatmap: yearly returns + CAGR column."""
    configure_chinese_matplotlib()
    yr = yearly_returns(nav)
    years = [int(y) for y in yr.index]
    yr_pct = yr.values * 100

    perf = performance_summary(nav, strategy_label)
    cagr_pct = perf["cagr"] * 100

    data = np.array([list(yr_pct) + [cagr_pct]])
    col_labels = [str(y) for y in years] + ["平均年化"]

    fig, ax = plt.subplots(figsize=(max(10, len(col_labels) * 0.9), 2.8))
    im = ax.imshow(data, aspect="auto", cmap="RdYlGn", vmin=-25, vmax=35)

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels)
    ax.set_yticks([0])
    ax.set_yticklabels([strategy_label])
    ax.set_title(f"{version_title} — {strategy_label} 分年收益 (%)")

    for j, val in enumerate(data[0]):
        if not np.isnan(val):
            color = "white" if abs(val) > 18 else "black"
            weight = "bold" if j == len(col_labels) - 1 else "normal"
            ax.text(j, 0, f"{val:.1f}", ha="center", va="center", fontsize=10, color=color, fontweight=weight)

    ax.axvline(len(years) - 0.5, color="white", linewidth=2)

    fig.colorbar(im, ax=ax, label="收益率 (%)", shrink=0.6)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
