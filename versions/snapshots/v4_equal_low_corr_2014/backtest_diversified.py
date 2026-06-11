"""
V4b: Equal-weight permanent portfolio after removing highly correlated equities.

Uses past lookback window to pick uncorrelated indices (no future data),
then equal-weights survivors inside the 25% stock sleeve.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from correlation_filter import correlation_matrix, select_stock_universe
from data_loader import (
    BOND_ETF_SPLICE_DATE,
    DATA_DIR,
    MULTI_COUNTRY_OTHER,
    _fetch_etf,
    _fetch_yfinance,
    load_spliced_bond_series,
    load_spliced_cash_series,
)
from expanded_study import EXPANDED_STOCKS
from metrics import format_summary_table, format_yearly_table, performance_summary, yearly_returns
from strategy_grouped import GroupedBacktestConfig, run_grouped_band_rebalance
from version_bundle import append_readme_note, snapshot_version

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "v4_equal_low_corr"
OUTPUT_DIR_SPLICED = Path(__file__).resolve().parent / "output" / "v4_equal_low_corr_2014"


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


def _cache_path(meta: dict) -> Path:
    if meta["type"] == "etf":
        return DATA_DIR / f"{meta['code']}.csv"
    code = meta["code"].lstrip("^").replace(".", "_")
    return DATA_DIR / f"yf_{code}.csv"


def _load_price_frame(meta: dict, start: str, end: str) -> pd.DataFrame:
    cache = _cache_path(meta)
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if cache.exists():
        part = pd.read_csv(cache, parse_dates=["date"])
        if part["date"].min() > start_ts or part["date"].max() < end_ts:
            try:
                fresh = (
                    _fetch_etf(meta["code"], start, end)
                    if meta["type"] == "etf"
                    else _fetch_yfinance(meta["code"], start, end)
                )
            except Exception:
                if meta["type"] == "etf" and meta["code"] in {"510300", "513100", "511260"}:
                    fresh = _fetch_yfinance(f"{meta['code']}.SS", start, end)
                elif meta["type"] == "etf":
                    raise
                else:
                    raise
            part = (
                pd.concat([part, fresh], ignore_index=True)
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date")
            )
            part.to_csv(cache, index=False)
    else:
        try:
            part = (
                _fetch_etf(meta["code"], start, end)
                if meta["type"] == "etf"
                else _fetch_yfinance(meta["code"], start, end)
            )
        except Exception:
            if meta["type"] == "etf" and meta["code"] in {"510300", "513100", "511260"}:
                part = _fetch_yfinance(f"{meta['code']}.SS", start, end)
            elif meta["type"] == "etf":
                raise
            else:
                raise
        part.to_csv(cache, index=False)
    return part[(part["date"] >= start_ts) & (part["date"] <= end_ts)]


def load_all_prices(
    start: str,
    end: str,
    bond_splice: bool = False,
) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    series: dict[str, pd.Series] = {}
    labels: dict[str, str] = {}
    for key, meta in EXPANDED_STOCKS.items():
        part = _load_price_frame(meta, start, end)
        series[key] = part.set_index("date")["close"].rename(key)
        labels[key] = f"{meta['name']}({meta['code']})"

    for key, meta in MULTI_COUNTRY_OTHER.items():
        if key == "bond" and bond_splice:
            series[key] = load_spliced_bond_series(start, end)
            labels[key] = f"国债(中债国债总指数→511260,切于{BOND_ETF_SPLICE_DATE})"
            continue
        if key == "cash" and bond_splice:
            series[key] = load_spliced_cash_series(start, end)
            labels[key] = f"现金(Shibor隔夜→511880,切于{BOND_ETF_SPLICE_DATE})"
            continue
        if meta.get("type") == "xau_usd":
            cache = DATA_DIR / f"{meta['code']}.csv"
            part = pd.read_csv(cache, parse_dates=["date"])
            if part["date"].min() > pd.Timestamp(start) or part["date"].max() < pd.Timestamp(end):
                from data_loader import _fetch_xau_cny

                fresh = _fetch_xau_cny(start, end)
                part = (
                    pd.concat([part, fresh], ignore_index=True)
                    .drop_duplicates("date")
                    .sort_values("date")
                )
                part.to_csv(cache, index=False)
            part = part[(part["date"] >= pd.Timestamp(start)) & (part["date"] <= pd.Timestamp(end))]
        else:
            part = _load_price_frame(meta, start, end)
        series[key] = part.set_index("date")["close"].rename(key)
        labels[key] = f"{meta['name']}({meta['code']})"

    stock_keys = list(EXPANDED_STOCKS.keys())
    cal = series["bond"].index
    prices = pd.DataFrame({k: series[k].reindex(cal).ffill() for k in series}).dropna(how="any")
    return prices, labels, stock_keys


def run_dynamic_equal_low_corr(
    prices: pd.DataFrame,
    all_stock_keys: list[str],
    lookback: int,
    corr_threshold: float,
    method: str,
    config: GroupedBacktestConfig,
    delay_band_to_noon: bool = False,
) -> tuple[pd.Series, pd.DataFrame, list[dict]]:
    """Reselect stock universe monthly; equal weight survivors; optional delayed band rebalance."""
    from schedule_rebalance import pick_rebalance_hour, scheduled_rebalance_due
    from strategy_grouped import _apply_rebalance, _group_weight

    hours = [12, 14, 10, 11, 13, 15, 9]
    assets = list(prices.columns)
    other_keys = config.other_keys
    rets = prices.pct_change()
    month_starts = set(prices.groupby(pd.Grouper(freq="MS")).head(1).index)
    dates = prices.index

    active_stocks = list(all_stock_keys)
    weight_map = {k: config.stock_sleeve / len(all_stock_keys) for k in all_stock_keys}
    for k in other_keys:
        weight_map[k] = config.other_sleeve
    target_vec = np.array([weight_map[a] for a in assets])
    px = prices.to_numpy(float)
    shares = (config.initial_capital * target_vec) / px[0]

    nav_list: list[float] = []
    weight_rows: list[np.ndarray] = []
    selection_log: list[dict] = []
    rebalance_log: list[dict] = []
    pending_band = False

    for i, date in enumerate(dates):
        values_arr = shares * px[i]

        if delay_band_to_noon and scheduled_rebalance_due(pending_band, date, dates, hours):
            new_values, cost = _apply_rebalance(values_arr, target_vec, config.transaction_cost)
            shares = np.where(px[i] > 0, new_values / px[i], 0.0)
            values_arr = shares * px[i]
            rebalance_log.append(
                {
                    "date": date,
                    "scheduled_hour_gmt8": pick_rebalance_hour(date, hours),
                    "transaction_cost": cost,
                }
            )
            pending_band = False

        if i > 0 and date in month_starts and i >= lookback:
            hist = rets.iloc[i - lookback : i][all_stock_keys]
            sel = select_stock_universe(hist, method=method, threshold=corr_threshold)
            active_stocks = sel["kept"]
            if active_stocks:
                weight_map = {k: 0.0 for k in all_stock_keys}
                per = config.stock_sleeve / len(active_stocks)
                for k in active_stocks:
                    weight_map[k] = per
                for k in other_keys:
                    weight_map[k] = config.other_sleeve
                target_vec = np.array([weight_map[a] for a in assets])
                values = shares * px[i]
                shares = (values.sum() * target_vec) / px[i]
                selection_log.append(
                    {
                        "date": date,
                        "kept": ",".join(active_stocks),
                        "dropped": ",".join(sel["dropped"]),
                        "n_kept": len(active_stocks),
                    }
                )

        values_arr = shares * px[i]
        total = values_arr.sum()
        groups = _group_weight({assets[j]: values_arr[j] for j in range(len(assets))}, all_stock_keys, other_keys)

        if i > 0:
            breached = any(g <= config.lower_band + 1e-12 for g in groups.values()) or any(
                g >= config.upper_band - 1e-12 for g in groups.values()
            )
            if breached:
                if delay_band_to_noon:
                    pending_band = True
                else:
                    new_values, _ = _apply_rebalance(values_arr, target_vec, config.transaction_cost)
                    shares = np.where(px[i] > 0, new_values / px[i], 0.0)
                    values_arr = shares * px[i]

        total = values_arr.sum()
        weight_rows.append(values_arr / total if total > 0 else target_vec)
        nav_list.append(total)

    nav = pd.Series(nav_list, index=dates, name="nav")
    weights = pd.DataFrame(weight_rows, index=dates, columns=assets)
    return nav, weights, selection_log, rebalance_log


def plot_corr(corr: pd.DataFrame, labels: dict[str, str], path: Path) -> None:
    cols = [labels.get(c, c) for c in corr.columns]
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(cols, fontsize=8)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{corr.values[i,j]:.2f}", ha="center", va="center", fontsize=7)
    ax.set_title("股票指数收益率相关系数 (252日)")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    out_dir = OUTPUT_DIR_SPLICED if args.bond_splice else OUTPUT_DIR
    if args.bond_splice and args.start == "2017-09-01":
        args.start = "2014-09-01"
    out_dir.mkdir(parents=True, exist_ok=True)

    prices, labels, stock_keys = load_all_prices(args.start, args.end, bond_splice=args.bond_splice)
    rets = prices[stock_keys].pct_change().dropna()

    # Full-sample reference selection (for display only)
    ref = select_stock_universe(rets.iloc[-args.lookback :], args.method, args.corr)
    plot_corr(ref["corr"], labels, out_dir / "correlation_matrix.png")

    config = GroupedBacktestConfig(
        stock_keys=stock_keys,
        lower_band=args.lower,
        upper_band=args.upper,
        initial_capital=args.capital,
    )

    # 去相关等权 — 带宽触发后延迟至 GMT+8 12:00（下一交易日执行，日线收盘价 proxy）
    nav_imm, _, sel_log, _ = run_dynamic_equal_low_corr(
        prices, stock_keys, args.lookback, args.corr, args.method, config, delay_band_to_noon=False
    )
    nav, weights, _, band_log = run_dynamic_equal_low_corr(
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

    # Latest selection
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

    snapshot_version(out_dir, ["backtest_diversified.py"])
    append_readme_note(out_dir, "backtest_diversified.py + 依赖模块")
    print(f"源码已写入: {(out_dir / 'src').resolve()}")


if __name__ == "__main__":
    main()
