"""
V4d: Equal-weight + corr filter + US Treasury bond sleeve + MMF cash.

Bond 25%: IEF (7-10Y US Treasury ETF) × USDCNH, CNY total return incl. coupon & duration.
Cash 25%: Shibor overnight → 511880 splice (2017-09).
Output: output/v4_equal_low_corr_美债/
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from backtest_diversified import (
    BOND_ETF_SPLICE_DATE,
    _load_price_frame,
    plot_corr,
    run_dynamic_equal_low_corr,
)
from correlation_filter import select_stock_universe
from data_loader import (
    DATA_DIR,
    MULTI_COUNTRY_OTHER,
    _fetch_xau_cny,
    load_spliced_cash_series,
    load_us_treasury_bond_series,
)
from expanded_study import EXPANDED_STOCKS
from metrics import format_summary_table, format_yearly_table, performance_summary, yearly_returns
from strategy_grouped import GroupedBacktestConfig

from version_bundle import append_readme_note, resolve_output_dir, snapshot_version

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

VERSION_NAME = "v4_equal_low_corr_美债"
OUTPUT_DIR = resolve_output_dir(VERSION_NAME)


def load_prices_us_tbond(start: str, end: str) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    series: dict[str, pd.Series] = {}
    labels: dict[str, str] = {}
    for key, meta in EXPANDED_STOCKS.items():
        part = _load_price_frame(meta, start, end)
        series[key] = part.set_index("date")["close"].rename(key)
        labels[key] = f"{meta['name']}({meta['code']})"

    gold_meta = MULTI_COUNTRY_OTHER["gold"]
    cache = DATA_DIR / f"{gold_meta['code']}.csv"
    gpart = pd.read_csv(cache, parse_dates=["date"])
    if gpart["date"].min() > pd.Timestamp(start):
        gpart = _fetch_xau_cny(start, end)
        gpart.to_csv(cache, index=False)
    gpart = gpart[(gpart["date"] >= pd.Timestamp(start)) & (gpart["date"] <= pd.Timestamp(end))]
    series["gold"] = gpart.set_index("date")["close"].rename("gold")
    labels["gold"] = f"{gold_meta['name']}({gold_meta['code']})"

    bond = load_us_treasury_bond_series(start, end)
    cash = load_spliced_cash_series(start, end)
    labels["bond"] = "美债(IEF 7-10Y×USDCNH,含票息久期)"
    labels["cash"] = f"货基(Shibor→511880,切于{BOND_ETF_SPLICE_DATE})"

    cal = series["gold"].index.intersection(bond.index).intersection(cash.index)
    prices = pd.DataFrame({k: series[k].reindex(cal).ffill() for k in series})
    prices["bond"] = bond.reindex(cal).ffill()
    prices["cash"] = cash.reindex(cal).ffill()
    prices = prices.dropna(how="any")
    return prices, labels, list(EXPANDED_STOCKS.keys())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2014-09-01")
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--corr", type=float, default=0.70)
    p.add_argument("--lookback", type=int, default=252)
    p.add_argument("--method", choices=["cluster", "greedy"], default="cluster")
    p.add_argument("--lower", type=float, default=0.21)
    p.add_argument("--upper", type=float, default=0.29)
    p.add_argument("--capital", type=float, default=1_000_000)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prices, labels, stock_keys = load_prices_us_tbond(args.start, args.end)
    rets = prices[stock_keys].pct_change().dropna()
    ref = select_stock_universe(rets.iloc[-args.lookback :], args.method, args.corr)
    plot_corr(ref["corr"], labels, OUTPUT_DIR / "correlation_matrix.png")

    config = GroupedBacktestConfig(stock_keys=stock_keys)
    nav, weights, sel_log, band_log = run_dynamic_equal_low_corr(
        prices,
        stock_keys,
        args.lookback,
        args.corr,
        args.method,
        config,
        delay_band_to_noon=True,
    )

    perf = performance_summary(nav, "美债+货基_GMT8中午调仓")
    summary = format_summary_table([perf])
    summary.to_csv(OUTPUT_DIR / "performance_summary.csv", encoding="utf-8-sig")
    pd.DataFrame(sel_log).to_csv(OUTPUT_DIR / "selection_log.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(band_log).to_csv(OUTPUT_DIR / "band_rebalance_log.csv", index=False, encoding="utf-8-sig")
    weights.iloc[-1].to_csv(OUTPUT_DIR / "latest_weights.csv", encoding="utf-8-sig")
    yearly_returns(nav).to_frame("GMT8中午调仓").to_csv(
        OUTPUT_DIR / "yearly_returns.csv", encoding="utf-8-sig"
    )

    with open(OUTPUT_DIR / "README.txt", "w", encoding="utf-8") as f:
        f.write("V4 等权 + 去相关 + 债券换美债 + 货基现金\n")
        f.write("债券 25%: IEF (美国7-10年国债ETF) × USDCNH\n")
        f.write("  - IEF 为总回报口径(含票息再投资+久期价格变动)\n")
        f.write("  - × USDCNH 表示人民币计价持有美元美债\n")
        f.write(f"现金 25%: {BOND_ETF_SPLICE_DATE} 前 Shibor隔夜, 之后 511880\n")
        f.write(f"区间: {prices.index.min().date()} ~ {prices.index.max().date()}\n")
        f.write(f"|corr|>{args.corr}, {args.method}, lookback={args.lookback}, GMT+8 中午调仓\n")

    print("=" * 60)
    print("V4 美债版: 债券=IEF×USDCNH, 现金=货基")
    print("=" * 60)
    print(f"区间: {prices.index.min().date()} ~ {prices.index.max().date()}")
    print("\n绩效:")
    print(summary.to_string())
    print(f"\n目录: {OUTPUT_DIR.resolve()}")

    snapshot_version(OUTPUT_DIR, ["backtest_diversified_us_tbond.py", "backtest_diversified.py"])
    append_readme_note(OUTPUT_DIR, "backtest_diversified_us_tbond.py + 依赖模块")
    print(f"源码已写入: {(OUTPUT_DIR / 'src').resolve()}")


if __name__ == "__main__":
    main()
