"""
V4b: Equal-weight permanent portfolio after removing highly correlated equities.

Uses past lookback window to pick uncorrelated indices (no future data),
then equal-weights survivors inside the 25% stock sleeve.
"""

from __future__ import annotations

import argparse

import pandas as pd

import _bootstrap  # noqa: F401
from _bootstrap import PROJECT_ROOT
from src.correlation_filter import select_stock_universe
from src.data import BOND_ETF_SPLICE_DATE
from src.metrics import format_summary_table, format_yearly_table, performance_summary, yearly_returns
from src.selection.dynamic_equal import load_all_prices, run_dynamic_equal_low_corr
from src.v4_common import make_v4_config
from src.version_bundle import append_readme_note, snapshot_version
from src.viz.correlation import plot_corr

OUTPUT_DIR = PROJECT_ROOT / "output" / "v4_equal_low_corr"
OUTPUT_DIR_SPLICED = PROJECT_ROOT / "output" / "v4_equal_low_corr_2014"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2017-09-01")
    p.add_argument("--end", default="2025-12-31")
    p.add_argument(
        "--bond-splice",
        action="store_true",
        help="2017-09 前用中债国债总指数，之后用 511260；输出到 v4_equal_low_corr_2014",
    )
    p.add_argument("--corr", type=float, default=0.70, help="|corr| threshold to treat as similar")
    p.add_argument("--lookback", type=int, default=252)
    p.add_argument("--method", choices=["cluster", "greedy"], default="cluster")
    p.add_argument("--lower", type=float, default=0.21)
    p.add_argument("--upper", type=float, default=0.29)
    p.add_argument("--capital", type=float, default=1_000_000)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = OUTPUT_DIR_SPLICED if args.bond_splice else OUTPUT_DIR
    if args.bond_splice and args.start == "2017-09-01":
        args.start = "2014-09-01"
    out_dir.mkdir(parents=True, exist_ok=True)

    prices, labels, stock_keys = load_all_prices(args.start, args.end, bond_splice=args.bond_splice)
    rets = prices[stock_keys].pct_change().dropna()

    ref = select_stock_universe(rets.iloc[-args.lookback :], args.method, args.corr)
    plot_corr(ref["corr"], labels, out_dir / "correlation_matrix.png")

    config = make_v4_config(args, stock_keys)

    nav_imm, _, sel_log, _, _ = run_dynamic_equal_low_corr(
        prices, stock_keys, args.lookback, args.corr, args.method, config, delay_band_to_noon=False
    )
    nav, weights, _, band_log, last_sel = run_dynamic_equal_low_corr(
        prices, stock_keys, args.lookback, args.corr, args.method, config, delay_band_to_noon=True
    )

    perf_imm = performance_summary(nav_imm, "去相关_收盘立即调仓")
    perf_filt = performance_summary(nav, "去相关_GMT8中午调仓")

    summary = format_summary_table([perf_imm, perf_filt])
    summary.to_csv(out_dir / "performance_summary.csv", encoding="utf-8-sig")
    pd.DataFrame(sel_log).to_csv(out_dir / "selection_log.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(band_log).to_csv(out_dir / "band_rebalance_log.csv", index=False, encoding="utf-8-sig")
    weights.iloc[-1].to_csv(out_dir / "latest_weights.csv", encoding="utf-8-sig")

    yearly_all = pd.DataFrame({"GMT8中午调仓": yearly_returns(nav)})
    yearly_all.to_csv(out_dir / "yearly_returns.csv", encoding="utf-8-sig")
    if args.bond_splice:
        seg = nav.loc["2014-01-01":"2017-12-31"]
        if len(seg) >= 2:
            yearly_seg = yearly_returns(seg).to_frame("GMT8中午调仓")
            seg_row = pd.Series(
                {"GMT8中午调仓": performance_summary(seg, "")["cagr"]},
                name="2014-2017年化",
            )
            pd.concat([yearly_seg, seg_row.to_frame().T]).to_csv(
                out_dir / "yearly_returns_2014_2017.csv", encoding="utf-8-sig"
            )

    if last_sel is None:
        last_sel = select_stock_universe(rets.iloc[-args.lookback :], args.method, args.corr)

    with open(out_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write("V4 等权 + 剔除高相关指数 + GMT+8 延迟调仓\n")
        if args.bond_splice:
            f.write(f"债券: {BOND_ETF_SPLICE_DATE} 前=中债国债总指数, 之后=511260 (拼接日水平对齐)\n")
            f.write(f"现金: {BOND_ETF_SPLICE_DATE} 前=Shibor隔夜合成, 之后=511880 (拼接日水平对齐)\n")
            f.write(f"回测区间: {prices.index.min().date()} ~ {prices.index.max().date()}\n")
        f.write(f"|corr| > {args.corr} 视为趋势相近，聚类后每簇保留1个\n")
        f.write(f"方法: {args.method}, 滚动 {args.lookback} 日, 每月初更新股票池\n")
        f.write("带宽触发: 不立即调仓; 下一 A 股交易日 GMT+8 12:00 统一调仓\n")
        f.write("若 12:00 不在交易时段则依次尝试 14/10/11/13/15/9 点 (日线用当日收盘价 proxy)\n")
        f.write(f"最近保留: {', '.join(last_sel['kept'])}\n")
        f.write(f"最近剔除: {', '.join(last_sel['dropped'])}\n")

    print("=" * 60)
    print("等权 + 剔除趋势相近指数")
    print("=" * 60)
    print(f"相关阈值: |r| > {args.corr}  |  方法: {args.method}")
    print(f"\n最近 {args.lookback} 日相关系数矩阵见: correlation_matrix.png")
    print("\n【最近一轮筛选】")
    print("保留:", ", ".join(f"{labels[k]} ({k})" for k in last_sel["kept"]))
    print("剔除:", ", ".join(f"{labels[k]} ({k})" for k in last_sel["dropped"]) or "(无)")
    print(f"\n保留 {len(last_sel['kept'])} 个 → 股票仓内各 {25/len(last_sel['kept']):.1f}%")
    print("\n最新全组合权重 (%):")
    w = weights.iloc[-1] * 100
    for k in w.index:
        print(f"  {labels.get(k,k)}: {w[k]:.2f}")
    print("\n绩效对比:")
    print(summary.to_string())
    if args.bond_splice:
        seg = nav.loc["2014-01-01":"2017-12-31"]
        if len(seg) >= 2:
            pseg = performance_summary(seg, "2014-2017")
            print(f"\n【2014-2017 子区间】{seg.index.min().date()} ~ {seg.index.max().date()}")
            print(f"  总收益 {pseg['total_return']*100:.2f}%  年化 {pseg['cagr']*100:.2f}%  "
                  f"夏普 {pseg['sharpe']:.2f}  回撤 {pseg['max_drawdown']*100:.2f}%")
            print(format_yearly_table(yearly_returns(seg).to_frame("GMT8中午调仓")).to_string())
    print(f"\n目录: {out_dir.resolve()}")

    snapshot_version(out_dir, ["versions/v4_equal_low_corr.py"])
    append_readme_note(out_dir, "versions/v4_equal_low_corr.py + 依赖模块")
    print(f"源码已写入: {(out_dir / 'src').resolve()}")


if __name__ == "__main__":
    main()
