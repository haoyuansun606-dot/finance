"""
Multi-country equal-weight equity permanent portfolio backtest.

Structure:
  - Stock sleeve 25%: equal weight across 5 global indices (yfinance)
  - Bond / cash / gold: 25% each (same as global preset)
  - Band rebalance on 4 groups (stock / bond / cash / gold) at ±4% default
"""

from __future__ import annotations

import argparse

import pandas as pd

import _bootstrap  # noqa: F401
from _bootstrap import PROJECT_ROOT
from src.data import MULTI_COUNTRY_EQUITIES, load_multi_country_prices
from src.metrics import format_summary_table, format_yearly_table, performance_summary, yearly_returns_table
from src.strategies.grouped import (
    GroupedBacktestConfig,
    run_grouped_band_rebalance,
    run_grouped_buy_and_hold,
    run_grouped_calendar_rebalance,
)
from src.viz.backtest import plot_backtest_comparison

OUTPUT_DIR = PROJECT_ROOT / "output" / "multicountry"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-country EW permanent portfolio")
    p.add_argument("--start", default="2017-09-01")
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--capital", type=float, default=1_000_000)
    p.add_argument("--lower", type=float, default=0.21)
    p.add_argument("--upper", type=float, default=0.29)
    p.add_argument("--cost", type=float, default=0.0)
    p.add_argument("--refresh", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    prices, labels, stock_keys = load_multi_country_prices(args.start, args.end, use_cache=not args.refresh)
    if prices.empty:
        raise RuntimeError("No overlapping price data.")

    config = GroupedBacktestConfig(
        stock_keys=stock_keys,
        lower_band=args.lower,
        upper_band=args.upper,
        initial_capital=args.capital,
        transaction_cost=args.cost,
    )

    band = run_grouped_band_rebalance(prices, config)
    bh = run_grouped_buy_and_hold(prices, config)
    annual = run_grouped_calendar_rebalance(prices, config)

    yearly_strategy = yearly_returns_table(
        {"带宽再平衡": band.nav, "买入持有": bh, "年末再平衡": annual.nav}
    )
    yearly_assets = yearly_returns_table({labels[k]: prices[k] for k in prices.columns})

    summaries = [
        performance_summary(band.nav, "带宽再平衡"),
        performance_summary(bh, "买入持有"),
        performance_summary(annual.nav, "年末再平衡"),
    ]
    summary_df = format_summary_table(summaries)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(OUTPUT_DIR / "performance_summary.csv", encoding="utf-8-sig")
    yearly_strategy.to_csv(OUTPUT_DIR / "yearly_strategy_returns.csv", encoding="utf-8-sig")
    yearly_assets.to_csv(OUTPUT_DIR / "yearly_asset_returns.csv", encoding="utf-8-sig")
    band.weights.to_csv(OUTPUT_DIR / "weights.csv", encoding="utf-8-sig")
    band.group_weights.to_csv(OUTPUT_DIR / "group_weights.csv", encoding="utf-8-sig")
    if not band.rebalance_log.empty:
        band.rebalance_log.to_csv(OUTPUT_DIR / "rebalance_log.csv", index=False, encoding="utf-8-sig")

    start = prices.index[0].date().isoformat()
    end = prices.index[-1].date().isoformat()
    chart = plot_backtest_comparison(
        band.nav,
        bh,
        annual.nav,
        prices,
        labels,
        len(band.rebalance_log),
        f"多国股指等权永久组合 ({start} ~ {end})",
        OUTPUT_DIR / "backtest_chart.png",
        stock_keys=stock_keys,
        figsize=(13, 8),
    )

    n = len(stock_keys)
    per = config.stock_sleeve / n

    print("=" * 60)
    print("多国股指等权 — 永久组合回测")
    print("=" * 60)
    print(f"区间: {start} ~ {end}  ({len(prices)} 日)")
    print(f"四大类: 股票 25% | 国债 25% | 货基 25% | 黄金 25%")
    print(f"股票内部等权: 每国 {per:.1%}（共 {n} 国）")
    print(f"带宽: [{args.lower:.0%}, {args.upper:.0%}]（按四大类触发）")
    print()
    print("全球股指:")
    for k in stock_keys:
        meta = MULTI_COUNTRY_EQUITIES[k]
        print(f"  - {meta['name']} ({meta['code']})")
    print()
    print("绩效:")
    print(summary_df.to_string())
    print()
    print("分年 — 组合策略:")
    print(format_yearly_table(yearly_strategy).to_string())
    print()
    print("分年 — 各资产:")
    print(format_yearly_table(yearly_assets).to_string())
    print()
    print(f"调仓次数: {len(band.rebalance_log)}")
    print(f"图表: {chart}")
    print(f"目录: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
