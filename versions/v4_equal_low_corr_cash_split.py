"""
V4c: Equal-weight + corr filter + bond splice + split cash sleeve.

Cash 25% = 5% CN demand deposit + 20% Dubai fixed deposit (US2Y×USDCNH proxy).
Output: output/v4_low_corr_cash_proxy/
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import _bootstrap  # noqa: F401
from src.correlation_filter import select_stock_universe
from src.data import BOND_ETF_SPLICE_DATE, DATA_DIR, MULTI_COUNTRY_OTHER, _fetch_xau_cny, load_split_cash_series, load_spliced_bond_series
from src.expanded_study import EXPANDED_STOCKS
from src.metrics import format_summary_table, format_yearly_table, performance_summary, yearly_returns
from src.selection.dynamic_equal import _load_price_frame, run_dynamic_equal_low_corr
from src.strategies.grouped import GroupedBacktestConfig
from src.version_bundle import append_readme_note, resolve_output_dir, snapshot_version
from src.viz.correlation import plot_corr

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

VERSION_NAME = "v4_low_corr_cash_proxy"
OUTPUT_DIR = resolve_output_dir(VERSION_NAME)


def load_prices_split_cash(start: str, end: str) -> tuple[pd.DataFrame, dict[str, str], list[str], pd.DataFrame]:
    """Load stocks + gold + spliced bond + split cash (skip 511880)."""
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

    bond = load_spliced_bond_series(start, end)
    cash, cash_d, cash_f = load_split_cash_series(start, end)
    labels["bond"] = f"国债(中债国债总指数→511260,切于{BOND_ETF_SPLICE_DATE})"
    labels["cash"] = "现金(5%活期+20%迪拜定存,占现金仓20:80)"
    labels["cash_demand"] = "活期(央行基准)"
    labels["cash_dubai_fixed"] = "迪拜定存(美2Y×USDCNH)"

    cal = bond.index
    prices = pd.DataFrame({k: series[k].reindex(cal).ffill() for k in series})
    prices["bond"] = bond.reindex(cal).ffill()
    prices["cash"] = cash.reindex(cal).ffill()
    prices = prices.dropna(how="any")

    components = pd.DataFrame({"cash_demand": cash_d, "cash_dubai_fixed": cash_f}).reindex(prices.index).ffill()
    stock_keys = list(EXPANDED_STOCKS.keys())
    return prices, labels, stock_keys, components


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

    prices, labels, stock_keys, cash_comp = load_prices_split_cash(args.start, args.end)
    rets = prices[stock_keys].pct_change().dropna()
    ref = select_stock_universe(rets.iloc[-args.lookback :], args.method, args.corr)
    plot_corr(ref["corr"], labels, OUTPUT_DIR / "correlation_matrix.png")

    config = GroupedBacktestConfig(
        stock_keys=stock_keys,
        lower_band=args.lower,
        upper_band=args.upper,
        initial_capital=args.capital,
    )

    nav, weights, sel_log, band_log = run_dynamic_equal_low_corr(
        prices, stock_keys, args.lookback, args.corr, args.method, config, delay_band_to_noon=True
    )

    perf = performance_summary(nav, "活5迪定20_GMT8中午调仓")
    summary = format_summary_table([perf])
    summary.to_csv(OUTPUT_DIR / "performance_summary.csv", encoding="utf-8-sig")
    pd.DataFrame(sel_log).to_csv(OUTPUT_DIR / "selection_log.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(band_log).to_csv(OUTPUT_DIR / "band_rebalance_log.csv", index=False, encoding="utf-8-sig")
    weights.iloc[-1].to_csv(OUTPUT_DIR / "latest_weights.csv", encoding="utf-8-sig")
    cash_comp.to_csv(OUTPUT_DIR / "cash_components.csv", encoding="utf-8-sig")

    yearly = yearly_returns(nav).to_frame("GMT8中午调仓")
    yearly.to_csv(OUTPUT_DIR / "yearly_returns.csv", encoding="utf-8-sig")

    seg = nav.loc["2014-01-01":"2017-12-31"]
    if len(seg) >= 2:
        yearly_seg = yearly_returns(seg).to_frame("GMT8中午调仓")
        seg_row = pd.Series({"GMT8中午调仓": performance_summary(seg, "")["cagr"]}, name="2014-2017年化")
        pd.concat([yearly_seg, seg_row.to_frame().T]).to_csv(
            OUTPUT_DIR / "yearly_returns_2014_2017.csv", encoding="utf-8-sig"
        )

    last_sel = select_stock_universe(rets.iloc[-args.lookback :], args.method, args.corr)
    with open(OUTPUT_DIR / "README.txt", "w", encoding="utf-8") as f:
        f.write("V4 等权 + 去相关 + 修改现金仓(替代511880货基)\n")
        f.write("全组合 25% 现金 = 5% 活期(央行基准) + 20% 迪拜定存\n")
        f.write("现金仓内部权重: 活期 20% + 迪拜定存 80%\n")
        f.write("迪拜定存 proxy: 美国国债2年收益率滚存 × USDCNH (迪拉姆挂钩美元)\n")
        f.write(f"债券: {BOND_ETF_SPLICE_DATE} 前中债国债总指数, 之后 511260\n")
        f.write(f"区间: {prices.index.min().date()} ~ {prices.index.max().date()}\n")
        f.write(f"|corr|>{args.corr}, {args.method}, lookback={args.lookback}, GMT+8 中午调仓\n")

    print("=" * 60)
    print("V4 修改货币基金: 5%活期 + 20%迪拜定存")
    print("=" * 60)
    print(f"区间: {prices.index.min().date()} ~ {prices.index.max().date()}")
    print("\n绩效:")
    print(summary.to_string())
    if len(seg) >= 2:
        pseg = performance_summary(seg, "2014-2017")
        print(f"\n2014-2017: 年化 {pseg['cagr']*100:.2f}%  回撤 {pseg['max_drawdown']*100:.2f}%")
        print(format_yearly_table(yearly_returns(seg).to_frame("组合")).to_string())
    print(f"\n目录: {OUTPUT_DIR.resolve()}")

    snapshot_version(OUTPUT_DIR, ["backtest_diversified_cash_split.py", "backtest_diversified.py"])
    append_readme_note(OUTPUT_DIR, "backtest_diversified_cash_split.py + 依赖模块")
    print(f"源码已写入: {(OUTPUT_DIR / 'src').resolve()}")


if __name__ == "__main__":
    main()
