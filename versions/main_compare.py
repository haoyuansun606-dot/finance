"""
Permanent Portfolio — 三策略一键对比

策略:
  1. 买入持有 (中国四资产，不调仓)
  2. 年末再平衡 (中国四资产，每年再平衡)
  3. 多国股指等权 (股票 25% 内等权 5 国 + 债/货/金各 25%，买入持有)

Usage:
  python main.py
  python main.py --start 2018-01-01 --end 2024-12-31
"""

from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401
from _bootstrap import PROJECT_ROOT
from src.data import ASSET_PRESETS, MULTI_COUNTRY_EQUITIES, asset_labels, load_multi_country_prices, load_prices
from src.metrics import format_summary_table, format_yearly_table, performance_summary, yearly_returns_table
from src.strategies.grouped import GroupedBacktestConfig, run_grouped_buy_and_hold
from src.strategies.standard import BacktestConfig, run_buy_and_hold, run_calendar_rebalance

OUTPUT_DIR = PROJECT_ROOT / "output" / "main_compare"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Permanent portfolio — 三策略对比")
    parser.add_argument("--start", default="2017-09-01", help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2025-12-31", help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=1_000_000, help="Initial capital in CNY")
    parser.add_argument("--cost", type=float, default=0.0, help="One-way transaction cost rate")
    parser.add_argument("--refresh", action="store_true", help="Re-download market data")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assets = ASSET_PRESETS["cn"]
    labels = asset_labels(assets)

    cn_prices = load_prices(
        start_date=args.start,
        end_date=args.end,
        assets=assets,
        use_cache=not args.refresh,
    )
    if cn_prices.empty:
        raise RuntimeError("No overlapping price data for CN assets in the selected range.")

    mc_prices, mc_labels, stock_keys = load_multi_country_prices(
        args.start, args.end, use_cache=not args.refresh
    )
    if mc_prices.empty:
        raise RuntimeError("No overlapping price data for multi-country assets.")

    cn_config = BacktestConfig(
        target_weight=0.25,
        initial_capital=args.capital,
        transaction_cost=args.cost,
    )
    mc_config = GroupedBacktestConfig(
        stock_keys=stock_keys,
        initial_capital=args.capital,
        transaction_cost=args.cost,
    )

    bh_nav = run_buy_and_hold(cn_prices, cn_config)
    annual = run_calendar_rebalance(cn_prices, cn_config)
    multi_nav = run_grouped_buy_and_hold(mc_prices, mc_config)

    summaries = [
        performance_summary(bh_nav, "买入持有(中国四资产)"),
        performance_summary(annual.nav, "年末再平衡(中国四资产)"),
        performance_summary(multi_nav, "多国股指等权(买入持有)"),
    ]
    summary_df = format_summary_table(summaries)

    yearly = yearly_returns_table(
        {
            "买入持有": bh_nav,
            "年末再平衡": annual.nav,
            "多国等权": multi_nav,
        }
    )
    yearly_fmt = format_yearly_table(yearly)

    effective_start = cn_prices.index[0].date().isoformat()
    effective_end = cn_prices.index[-1].date().isoformat()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(OUTPUT_DIR / "performance_summary.csv", encoding="utf-8-sig")
    yearly.to_csv(OUTPUT_DIR / "yearly_returns.csv", encoding="utf-8-sig")

    print("=" * 60)
    print("永久组合 — 三策略对比")
    print("=" * 60)
    print(f"样本区间: {effective_start} ~ {effective_end}")
    print(f"初始资金: {args.capital:,.0f} 元")
    print()
    print("中国四资产代理:")
    for key, text in labels.items():
        print(f"  - {key}: {text}")
    print()
    print("多国版 — 股票内部等权:")
    for k in stock_keys:
        meta = MULTI_COUNTRY_EQUITIES[k]
        print(f"  - {meta['name']} ({meta['code']})")
    print()
    print("绩效对比:")
    print(summary_df.to_string())
    print()
    print("分年收益:")
    print(yearly_fmt.to_string())
    print()
    print(f"结果已保存: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
