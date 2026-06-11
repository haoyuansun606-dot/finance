"""Backtest NAV and drawdown charts."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.viz.style import configure_chinese_matplotlib


def plot_backtest_comparison(
    band_nav: pd.Series,
    bh_nav: pd.Series,
    annual_nav: pd.Series,
    asset_prices: pd.DataFrame,
    labels: dict[str, str],
    rebalance_count: int,
    title: str,
    out_path: Path,
    stock_keys: list[str] | None = None,
    figsize: tuple[float, float] = (12, 8),
) -> Path:
    """
    Plot normalized NAV for three strategies plus underlying assets.

    If stock_keys is None (CN preset), all assets use the same line style.
    If stock_keys is set (multi-country), equities vs other sleeves differ.
    """
    configure_chinese_matplotlib()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    norm = lambda s: s / s.iloc[0]

    fig, axes = plt.subplots(2, 1, figsize=figsize, gridspec_kw={"height_ratios": [3, 1]})
    ax = axes[0]
    ax.plot(band_nav.index, norm(band_nav), label=f"带宽再平衡 (调仓 {rebalance_count} 次)", linewidth=2)
    ax.plot(bh_nav.index, norm(bh_nav), label="买入持有(不调仓)" if stock_keys is None else "买入持有", linestyle="--", alpha=0.85)
    ax.plot(annual_nav.index, norm(annual_nav), label="年末再平衡", linestyle=":", alpha=0.85)

    for col in asset_prices.columns:
        if stock_keys is None:
            ax.plot(asset_prices.index, norm(asset_prices[col]), label=labels[col], alpha=0.45, linewidth=1)
        else:
            style = "-" if col in stock_keys else "--"
            lw = 1.2 if col in stock_keys else 0.9
            ax.plot(
                asset_prices.index,
                norm(asset_prices[col]),
                label=labels[col],
                alpha=0.5,
                linewidth=lw,
                linestyle=style,
            )

    ax.set_title(title)
    ax.set_ylabel("净值 (归一化)")
    legend_kwargs = {"loc": "upper left", "fontsize": 9}
    if stock_keys is not None:
        legend_kwargs = {"loc": "upper left", "fontsize": 7, "ncol": 2}
    ax.legend(**legend_kwargs)
    ax.grid(True, alpha=0.3)

    dd = band_nav / band_nav.cummax() - 1
    axes[1].fill_between(dd.index, dd, 0, color="tab:red", alpha=0.35)
    axes[1].set_ylabel("回撤")
    axes[1].set_xlabel("日期")
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
