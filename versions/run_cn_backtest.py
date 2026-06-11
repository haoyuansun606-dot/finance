"""
Permanent Portfolio backtest (永久组合 + 带宽再平衡)

Strategy:
  - 25% each: broad index, long-term gov bond, money market, gold
  - Rebalance to 25% when any sleeve <= 21% or >= 29%

Default China ETF proxies:
  - 510300 沪深300ETF
  - 511260 十年国债ETF
  - 511880 银华日利 (money-market proxy)
  - 518880 黄金ETF

Usage:
  python backtest.py
  python backtest.py --start 2018-01-01 --end 2024-12-31 --cost 0.001
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import _bootstrap  # noqa: F401
from _bootstrap import PROJECT_ROOT
from src.data import ASSET_PRESETS, asset_labels, load_prices
from src.metrics import format_summary_table, format_yearly_table, performance_summary, yearly_returns_table
from src.strategies.standard import BacktestConfig, run_band_rebalance, run_buy_and_hold, run_calendar_rebalance
from src.viz.backtest import plot_backtest_comparison

OUTPUT_DIR = PROJECT_ROOT / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Permanent portfolio band-rebalance backtest")
    parser.add_argument("--start", default="2017-09-01", help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2025-12-31", help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=1_000_000, help="Initial capital in CNY")
    parser.add_argument("--target", type=float, default=0.25, help="Target weight per sleeve")
    parser.add_argument("--lower", type=float, default=0.21, help="Lower rebalance band")
    parser.add_argument("--upper", type=float, default=0.29, help="Upper rebalance band")
    parser.add_argument("--cost", type=float, default=0.0, help="One-way transaction cost rate")
    parser.add_argument("--preset", choices=["cn", "global"], default="cn", help="Asset preset")
    parser.add_argument("--refresh", action="store_true", help="Re-download market data")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assets = ASSET_PRESETS[args.preset]
    labels = asset_labels(assets)
    output_dir = OUTPUT_DIR / args.preset

    prices = load_prices(
        start_date=args.start,
        end_date=args.end,
        assets=assets,
        use_cache=not args.refresh,
    )
    if prices.empty:
        raise RuntimeError("No overlapping price data for all assets in the selected range.")

    effective_start = prices.index[0].date().isoformat()
    effective_end = prices.index[-1].date().isoformat()

    config = BacktestConfig(
        target_weight=args.target,
        lower_band=args.lower,
        upper_band=args.upper,
        initial_capital=args.capital,
        transaction_cost=args.cost,
    )

    band = run_band_rebalance(prices, config)
    bh_nav = run_buy_and_hold(prices, config)
    annual = run_calendar_rebalance(prices, config)

    asset_navs = prices / prices.iloc[0] * args.capital

    yearly_strategy = yearly_returns_table(
        {
            "带宽再平衡": band.nav,
            "买入持有": bh_nav,
            "年末再平衡": annual.nav,
        }
    )
    yearly_assets = yearly_returns_table({labels[k]: prices[k] for k in prices.columns})
    yearly_strategy_fmt = format_yearly_table(yearly_strategy)
    yearly_assets_fmt = format_yearly_table(yearly_assets)

    summaries = [
        performance_summary(band.nav, "带宽再平衡(21%/29%)"),
        performance_summary(bh_nav, "买入持有(不调仓)"),
        performance_summary(annual.nav, "年末再平衡"),
    ]
    summary_df = format_summary_table(summaries)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(output_dir / "performance_summary.csv", encoding="utf-8-sig")
    band.nav.to_csv(output_dir / "band_rebalance_nav.csv", encoding="utf-8-sig")
    band.weights.to_csv(output_dir / "band_rebalance_weights.csv", encoding="utf-8-sig")
    yearly_strategy.to_csv(output_dir / "yearly_strategy_returns.csv", encoding="utf-8-sig")
    yearly_assets.to_csv(output_dir / "yearly_asset_returns.csv", encoding="utf-8-sig")
    if not band.rebalance_log.empty:
        band.rebalance_log.to_csv(output_dir / "rebalance_log.csv", index=False, encoding="utf-8-sig")

    chart_path = plot_backtest_comparison(
        band.nav,
        bh_nav,
        annual.nav,
        asset_navs,
        labels,
        len(band.rebalance_log),
        f"永久组合回测 ({effective_start} ~ {effective_end})",
        output_dir / "backtest_chart.png",
    )

    print("=" * 60)
    print("永久组合回测 — 四等分 + 带宽再平衡")
    print("=" * 60)
    print(f"样本区间: {effective_start} ~ {effective_end}  ({len(prices)} 个交易日)")
    print(f"初始资金: {args.capital:,.0f} 元")
    print(f"目标权重: 各 {args.target:.0%}  |  触发带: [{args.lower:.0%}, {args.upper:.0%}]")
    print()
    print("资产代理:")
    for key, text in labels.items():
        print(f"  - {key}: {text}")
    print()
    print("绩效对比:")
    print(summary_df.to_string())
    print()
    print("分年收益 — 组合策略:")
    print(yearly_strategy_fmt.to_string())
    print()
    print("分年收益 — 各类资产:")
    print(yearly_assets_fmt.to_string())
    print()
    print(f"带宽策略调仓次数: {len(band.rebalance_log)}")
    if not band.rebalance_log.empty:
        print("最近 5 次调仓:")
        print(band.rebalance_log.tail(5).to_string(index=False))
    print()
    print(f"图表已保存: {chart_path}")
    print(f"结果目录: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
