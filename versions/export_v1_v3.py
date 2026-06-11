"""Export v1/v2/v3 backtests with simplified yearly heatmaps."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import _bootstrap  # noqa: F401
from _bootstrap import PROJECT_ROOT
from src.data import ASSET_PRESETS, load_multi_country_prices, load_prices
from src.metrics import format_summary_table, performance_summary, yearly_returns
from src.strategies.grouped import (
    GroupedBacktestConfig,
    run_grouped_band_rebalance,
    run_grouped_buy_and_hold,
    run_grouped_calendar_rebalance,
)
from src.strategies.standard import BacktestConfig, run_band_rebalance, run_buy_and_hold, run_calendar_rebalance
from src.viz.heatmap import plot_yearly_heatmap

OUTPUT_ROOT = PROJECT_ROOT / "output"

VERSIONS = {
    "v1_cn": {
        "title": "V1 沪深300 + 黄金ETF",
        "preset": "cn",
        "grouped": False,
    },
    "v2_global": {
        "title": "V2 纳指 + XAUUSD",
        "preset": "global",
        "grouped": False,
    },
    "v3_multicountry": {
        "title": "V3 五国股指等权 + XAUUSD",
        "preset": None,
        "grouped": True,
    },
}

STRATEGIES = [
    ("band", "带宽再平衡"),
    ("bh", "买入持有"),
    ("annual", "年末再平衡"),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2017-09-01")
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--capital", type=float, default=1_000_000)
    p.add_argument("--lower", type=float, default=0.21)
    p.add_argument("--upper", type=float, default=0.29)
    return p.parse_args()


def _run_standard(prices: pd.DataFrame, capital: float, lower: float, upper: float) -> dict[str, pd.Series]:
    config = BacktestConfig(
        target_weight=0.25,
        lower_band=lower,
        upper_band=upper,
        initial_capital=capital,
    )
    band = run_band_rebalance(prices, config)
    bh = run_buy_and_hold(prices, config)
    annual = run_calendar_rebalance(prices, config)
    return {"band": band.nav, "bh": bh, "annual": annual.nav}


def _run_grouped(prices: pd.DataFrame, stock_keys: list[str], capital: float, lower: float, upper: float) -> dict[str, pd.Series]:
    config = GroupedBacktestConfig(
        stock_keys=stock_keys,
        lower_band=lower,
        upper_band=upper,
        initial_capital=capital,
    )
    band = run_grouped_band_rebalance(prices, config)
    bh = run_grouped_buy_and_hold(prices, config)
    annual = run_grouped_calendar_rebalance(prices, config)
    return {"band": band.nav, "bh": bh, "annual": annual.nav}


def export_version(
    version_key: str,
    meta: dict,
    navs: dict[str, pd.Series],
    start: str,
    end: str,
) -> Path:
    out_dir = OUTPUT_ROOT / version_key
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_df = format_summary_table(
        [performance_summary(navs[key], label) for key, label in STRATEGIES]
    )
    summary_df.to_csv(out_dir / "performance_summary.csv", encoding="utf-8-sig")

    for key, label in STRATEGIES:
        plot_yearly_heatmap(navs[key], label, meta["title"], out_dir / f"heatmap_{key}.png")

    yearly_df = pd.DataFrame({label: yearly_returns(navs[key]) for key, label in STRATEGIES})
    cagr_row = pd.Series(
        {label: performance_summary(navs[key], label)["cagr"] for key, label in STRATEGIES},
        name="平均年化",
    )
    yearly_df = pd.concat([yearly_df, cagr_row.to_frame().T])
    yearly_df.index.name = "year"
    yearly_df.to_csv(out_dir / "yearly_strategy_returns.csv", encoding="utf-8-sig")

    with open(out_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(f"{meta['title']}\n")
        f.write(f"区间: {start} ~ {end}\n")
        f.write("图表: heatmap_band.png / heatmap_bh.png / heatmap_annual.png\n")

    return out_dir


def main() -> None:
    args = parse_args()

    for version_key, meta in VERSIONS.items():
        print(f"Export {version_key}: {meta['title']} ...")
        if meta["grouped"]:
            prices, _, stock_keys = load_multi_country_prices(args.start, args.end)
            navs = _run_grouped(prices, stock_keys, args.capital, args.lower, args.upper)
            start = prices.index[0].date().isoformat()
            end = prices.index[-1].date().isoformat()
        else:
            prices = load_prices(args.start, args.end, assets=ASSET_PRESETS[meta["preset"]])
            navs = _run_standard(prices, args.capital, args.lower, args.upper)
            start = prices.index[0].date().isoformat()
            end = prices.index[-1].date().isoformat()

        out = export_version(version_key, meta, navs, start, end)
        print(f"  -> {out}")

    print(f"\nDone. Root: {OUTPUT_ROOT.resolve()}")


if __name__ == "__main__":
    main()
