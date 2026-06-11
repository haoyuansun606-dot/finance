"""Sharpe / drawdown comparison bar charts."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.viz.style import configure_chinese_matplotlib


def plot_sharpe_drawdown_bars(
    summary: pd.DataFrame,
    scheme_labels: dict[str, str],
    title: str,
    out_path: Path,
    scheme_col: str = "scheme",
) -> Path:
    configure_chinese_matplotlib()
    names = [scheme_labels.get(s, s) for s in summary[scheme_col]]
    x = np.arange(len(summary))

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].bar(x, summary["sharpe"], color="#2563eb", alpha=0.85)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(names, rotation=15, ha="right")
    axes[0].set_title("夏普比率")
    axes[0].grid(True, axis="y", alpha=0.3)

    axes[1].bar(x, summary["max_drawdown"] * 100, color="#dc2626", alpha=0.85)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(names, rotation=15, ha="right")
    axes[1].set_title("最大回撤 (%)")
    axes[1].grid(True, axis="y", alpha=0.3)

    fig.suptitle(title, fontsize=12)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
