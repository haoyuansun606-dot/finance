"""
Visualize yearly returns across bandwidth settings for both asset presets.

Generates multiple charts under output/visualizations/
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401
from _bootstrap import PROJECT_ROOT
from src.data import ASSET_PRESETS, load_prices
from src.metrics import yearly_returns, yearly_returns_table
from src.strategies.standard import BacktestConfig, run_band_rebalance, run_buy_and_hold, run_calendar_rebalance

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUT_DIR = PROJECT_ROOT / "output" / "visualizations"

BAND_SETTINGS = [
    (0.22, 0.28, "±3%"),
    (0.21, 0.29, "±4%"),
    (0.20, 0.30, "±5%"),
    (0.19, 0.31, "±6%"),
    (0.18, 0.32, "±7%"),
    (0.15, 0.35, "±10%"),
]

PRESET_LABELS = {
    "global": "纳指 + XAUUSD",
    "cn": "沪深300 + 黄金ETF",
}

STRATEGIES = ["带宽再平衡", "买入持有", "年末再平衡"]
STRATEGY_COLORS = {
    "带宽再平衡": "#2563eb",
    "买入持有": "#f97316",
    "年末再平衡": "#16a34a",
}
BAND_CMAP = plt.cm.viridis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualize band-rebalance sweep")
    parser.add_argument("--start", default="2017-09-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--capital", type=float, default=1_000_000)
    return parser.parse_args()


def run_sweep(prices: pd.DataFrame, capital: float) -> dict[str, pd.DataFrame]:
    """Return {band_label: DataFrame(year x 3 strategies)}."""
    results: dict[str, pd.DataFrame] = {}
    for lower, upper, label in BAND_SETTINGS:
        config = BacktestConfig(
            target_weight=0.25,
            lower_band=lower,
            upper_band=upper,
            initial_capital=capital,
        )
        band = run_band_rebalance(prices, config)
        bh = run_buy_and_hold(prices, config)
        annual = run_calendar_rebalance(prices, config)
        results[label] = yearly_returns_table(
            {
                "带宽再平衡": band.nav,
                "买入持有": bh,
                "年末再平衡": annual.nav,
            }
        )
    return results


def _years_from_results(results: dict[str, pd.DataFrame]) -> list[int]:
    years: set[int] = set()
    for df in results.values():
        years.update(int(y) for y in df.index)
    return sorted(years)


def plot_grouped_bars_by_band(preset: str, results: dict[str, pd.DataFrame]) -> Path:
    """6 subplots: each bandwidth, grouped bars for 3 strategies per year."""
    years = _years_from_results(results)
    x = np.arange(len(years))
    width = 0.25

    fig, axes = plt.subplots(2, 3, figsize=(18, 10), sharey=True)
    fig.suptitle(f"{PRESET_LABELS[preset]} — 分年收益（三种策略 × 六种带宽）", fontsize=14, y=1.01)

    for ax, (_, _, label) in zip(axes.flat, BAND_SETTINGS):
        df = results[label].reindex(years)
        for i, strat in enumerate(STRATEGIES):
            vals = df[strat].values * 100
            ax.bar(x + (i - 1) * width, vals, width, label=strat, color=STRATEGY_COLORS[strat], alpha=0.88)
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.set_title(f"带宽 {label}", fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels(years, rotation=45)
        ax.set_ylabel("收益率 (%)")
        ax.grid(True, axis="y", alpha=0.25)

    handles, labels_ = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels_, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.04), frameon=False)
    fig.tight_layout()
    path = OUT_DIR / f"{preset}_01_grouped_bars_by_band.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_strategy_lines_by_band(preset: str, results: dict[str, pd.DataFrame]) -> Path:
    """3 rows (strategies), each shows 6 bandwidth lines over years."""
    years = _years_from_results(results)
    band_labels = [b[2] for b in BAND_SETTINGS]
    colors = BAND_CMAP(np.linspace(0.15, 0.9, len(BAND_SETTINGS)))

    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
    fig.suptitle(f"{PRESET_LABELS[preset]} — 分年收益走势（按策略分面）", fontsize=14)

    for ax, strat in zip(axes, STRATEGIES):
        for (lower, upper, blabel), color in zip(BAND_SETTINGS, colors):
            s = results[blabel][strat].reindex(years) * 100
            ax.plot(years, s, marker="o", linewidth=1.8, markersize=5, label=f"带宽 {blabel}", color=color)
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.set_title(strat, fontsize=12)
        ax.set_ylabel("收益率 (%)")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left", fontsize=8, ncol=3)

    axes[-1].set_xlabel("年份")
    fig.tight_layout()
    path = OUT_DIR / f"{preset}_02_strategy_lines_by_band.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_heatmap_band_rebalance(preset: str, results: dict[str, pd.DataFrame]) -> Path:
    """Heatmap: rows=bandwidth, cols=years, values=band-rebalance return."""
    years = _years_from_results(results)
    band_labels = [b[2] for b in BAND_SETTINGS]
    data = np.array([results[bl].loc[years, "带宽再平衡"].values * 100 for bl in band_labels])

    fig, ax = plt.subplots(figsize=(12, 5))
    im = ax.imshow(data, aspect="auto", cmap="RdYlGn", vmin=-15, vmax=35)
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years)
    ax.set_yticks(range(len(band_labels)))
    ax.set_yticklabels(band_labels)
    ax.set_xlabel("年份")
    ax.set_ylabel("带宽")
    ax.set_title(f"{PRESET_LABELS[preset]} — 带宽再平衡 分年收益热力图 (%)")

    for i in range(len(band_labels)):
        for j in range(len(years)):
            val = data[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=8, color="black")

    fig.colorbar(im, ax=ax, label="收益率 (%)", shrink=0.85)
    fig.tight_layout()
    path = OUT_DIR / f"{preset}_03_band_rebalance_heatmap.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_heatmap_all_strategies(preset: str, results: dict[str, pd.DataFrame], band_label: str = "±4%") -> Path:
    """One bandwidth: 3 strategy heatmaps side by side (single row)."""
    years = _years_from_results(results)
    df = results[band_label].reindex(years)

    fig, axes = plt.subplots(1, 3, figsize=(16, 3.5))
    fig.suptitle(f"{PRESET_LABELS[preset]} — 带宽 {band_label} 三种策略分年对比", fontsize=13)

    for ax, strat in zip(axes, STRATEGIES):
        vals = df[strat].values * 100
        colors_list = ["#d73027" if v < 0 else "#1a9850" for v in vals]
        ax.bar(years, vals, color=colors_list, alpha=0.85, edgecolor="white")
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.set_title(strat)
        ax.set_xlabel("年份")
        ax.set_ylabel("收益率 (%)")
        ax.grid(True, axis="y", alpha=0.25)
        for x, v in zip(years, vals):
            if not np.isnan(v):
                ax.text(x, v + (1.2 if v >= 0 else -2.5), f"{v:.1f}%", ha="center", va="bottom" if v >= 0 else "top", fontsize=7)

    fig.tight_layout()
    safe = band_label.replace("±", "pm")
    path = OUT_DIR / f"{preset}_04_three_strategies_band_{safe}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_all_bands_one_strategy(preset: str, results: dict[str, pd.DataFrame], strategy: str = "带宽再平衡") -> Path:
    """Grouped bars: x=year, groups=bandwidth (6 bars per year)."""
    years = _years_from_results(results)
    band_labels = [b[2] for b in BAND_SETTINGS]
    x = np.arange(len(years))
    width = 0.13
    colors = BAND_CMAP(np.linspace(0.15, 0.9, len(band_labels)))

    fig, ax = plt.subplots(figsize=(16, 6))
    for i, bl in enumerate(band_labels):
        vals = results[bl].reindex(years)[strategy].values * 100
        offset = (i - (len(band_labels) - 1) / 2) * width
        ax.bar(x + offset, vals, width, label=f"带宽 {bl}", color=colors[i], alpha=0.9)

    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(years)
    ax.set_xlabel("年份")
    ax.set_ylabel("收益率 (%)")
    ax.set_title(f"{PRESET_LABELS[preset]} — {strategy}：各带宽分年收益对比")
    ax.legend(loc="upper left", ncol=3, fontsize=9)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    safe = "band" if strategy == "带宽再平衡" else "bh" if strategy == "买入持有" else "annual"
    path = OUT_DIR / f"{preset}_05_{safe}_all_bands_grouped.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_preset_comparison(all_results: dict[str, dict[str, pd.DataFrame]], strategy: str = "带宽再平衡") -> Path:
    """Compare global vs cn for band-rebalance, heatmap style 2 rows."""
    years = _years_from_results(all_results["global"])
    band_labels = [b[2] for b in BAND_SETTINGS]

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    for ax, preset in zip(axes, ["global", "cn"]):
        data = np.array([all_results[preset][bl].loc[years, strategy].values * 100 for bl in band_labels])
        im = ax.imshow(data, aspect="auto", cmap="RdYlGn", vmin=-15, vmax=35)
        ax.set_yticks(range(len(band_labels)))
        ax.set_yticklabels(band_labels)
        ax.set_ylabel("带宽")
        ax.set_title(PRESET_LABELS[preset])
        for i in range(len(band_labels)):
            for j in range(len(years)):
                val = data[i, j]
                if not np.isnan(val):
                    ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=7, color="black")

    axes[-1].set_xticks(range(len(years)))
    axes[-1].set_xticklabels(years)
    axes[-1].set_xlabel("年份")
    fig.suptitle(f"两套资产 — {strategy} 分年收益对比 (%)", fontsize=14)
    fig.colorbar(im, ax=axes, label="收益率 (%)", shrink=0.7)
    fig.tight_layout()
    safe = {"带宽再平衡": "band", "买入持有": "bh", "年末再平衡": "annual"}[strategy]
    path = OUT_DIR / f"compare_06_presets_{safe}_heatmap.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_cumulative_yearly_diff(preset: str, results: dict[str, pd.DataFrame]) -> Path:
    """Full-period total return by bandwidth for 3 strategies (bar chart)."""
    band_labels = [b[2] for b in BAND_SETTINGS]
    totals = {bl: {} for bl in band_labels}
    for bl in band_labels:
        for strat in STRATEGIES:
            s = results[bl][strat].dropna()
            totals[bl][strat] = (1 + s).prod() - 1

    x = np.arange(len(band_labels))
    width = 0.25
    fig, ax = plt.subplots(figsize=(12, 6))
    for i, strat in enumerate(STRATEGIES):
        vals = [totals[bl][strat] * 100 for bl in band_labels]
        ax.bar(x + (i - 1) * width, vals, width, label=strat, color=STRATEGY_COLORS[strat], alpha=0.88)

    ax.set_xticks(x)
    ax.set_xticklabels([f"带宽 {bl}" for bl in band_labels], rotation=15)
    ax.set_ylabel("累计复合收益 (%)")
    ax.set_title(f"{PRESET_LABELS[preset]} — 2017-2025 累计收益（由分年复合）")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    path = OUT_DIR / f"{preset}_07_cumulative_by_band.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_year_facets_one_band(preset: str, results: dict[str, pd.DataFrame], band_label: str = "±4%") -> Path:
    """Small multiples: one subplot per year, 3 bars (strategies)."""
    years = _years_from_results(results)
    df = results[band_label].reindex(years)
    n = len(years)
    cols = 3
    rows = int(np.ceil(n / cols))

    fig, axes = plt.subplots(rows, cols, figsize=(14, 3.5 * rows))
    fig.suptitle(f"{PRESET_LABELS[preset]} — 带宽 {band_label} 逐年三策略对比", fontsize=14)
    axes_flat = np.array(axes).flatten()

    for idx, year in enumerate(years):
        ax = axes_flat[idx]
        vals = [df.loc[year, s] * 100 for s in STRATEGIES]
        bars = ax.bar(STRATEGIES, vals, color=[STRATEGY_COLORS[s] for s in STRATEGIES], alpha=0.88)
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.set_title(str(year))
        ax.set_ylabel("%")
        ax.tick_params(axis="x", rotation=20, labelsize=8)
        ax.grid(True, axis="y", alpha=0.25)
        for bar, v in zip(bars, vals):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.1f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=7)

    for j in range(n, len(axes_flat)):
        axes_flat[j].set_visible(False)

    fig.tight_layout()
    safe = band_label.replace("±", "pm")
    path = OUT_DIR / f"{preset}_08_yearly_facets_band_{safe}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def save_csv(all_results: dict[str, dict[str, pd.DataFrame]]) -> None:
    rows = []
    for preset, results in all_results.items():
        for bl in [b[2] for b in BAND_SETTINGS]:
            df = results[bl]
            for year in df.index:
                for strat in STRATEGIES:
                    rows.append(
                        {
                            "preset": preset,
                            "preset_label": PRESET_LABELS[preset],
                            "band": bl,
                            "year": int(year),
                            "strategy": strat,
                            "return": df.loc[year, strat],
                        }
                    )
    pd.DataFrame(rows).to_csv(OUT_DIR / "yearly_returns_sweep.csv", index=False, encoding="utf-8-sig")


def main() -> None:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, dict[str, pd.DataFrame]] = {}
    saved: list[Path] = []

    for preset in ["global", "cn"]:
        print(f"Running sweep: {PRESET_LABELS[preset]} ...")
        prices = load_prices(args.start, args.end, assets=ASSET_PRESETS[preset])
        all_results[preset] = run_sweep(prices, args.capital)

        saved.append(plot_grouped_bars_by_band(preset, all_results[preset]))
        saved.append(plot_strategy_lines_by_band(preset, all_results[preset]))
        saved.append(plot_heatmap_band_rebalance(preset, all_results[preset]))
        for bl in ["±3%", "±4%", "±5%", "±6%", "±7%", "±10%"]:
            saved.append(plot_heatmap_all_strategies(preset, all_results[preset], bl))
            saved.append(plot_year_facets_one_band(preset, all_results[preset], bl))
        saved.append(plot_all_bands_one_strategy(preset, all_results[preset], "带宽再平衡"))
        saved.append(plot_all_bands_one_strategy(preset, all_results[preset], "买入持有"))
        saved.append(plot_all_bands_one_strategy(preset, all_results[preset], "年末再平衡"))
        saved.append(plot_cumulative_yearly_diff(preset, all_results[preset]))

    saved.append(plot_preset_comparison(all_results, "带宽再平衡"))
    saved.append(plot_preset_comparison(all_results, "买入持有"))
    saved.append(plot_preset_comparison(all_results, "年末再平衡"))
    save_csv(all_results)

    print("=" * 60)
    print(f"区间: {args.start} ~ {args.end}")
    print(f"共生成 {len(saved)} 张图 + 1 个 CSV")
    print(f"目录: {OUT_DIR.resolve()}")
    for p in saved:
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()
