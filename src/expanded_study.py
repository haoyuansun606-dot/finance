"""
V4: Expanded global equity sleeve inside permanent portfolio.

Combines previously used indices (CSI300, Nasdaq, US/JP/UK/DE/HK from v3)
PLUS new: Vietnam, Singapore, Korea.

Structure: stock 25% (split across all indices) | bond 25% | cash 25% | gold 25%
Band rebalance on 4 groups (default ±4%). Stock internal weights refreshed monthly.

Focus: Sharpe ratio & max drawdown across weighting schemes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.data import DATA_DIR, MULTI_COUNTRY_OTHER, _fetch_etf, _fetch_xau_cny, _fetch_yfinance
from src.metrics import performance_summary
from src.strategies.grouped import GroupedBacktestConfig, run_grouped_adaptive_stocks, run_grouped_band_rebalance
from src.viz.schemes import plot_sharpe_drawdown_bars

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "v4_extended"

# Previously used + newly added (within 25% stock sleeve)
EXPANDED_STOCKS = {
    "cn": {"code": "510300", "name": "沪深300", "type": "etf", "tag": "v1"},
    "nasdaq": {"code": "513100", "name": "纳指100", "type": "etf", "tag": "v2"},
    "us": {"code": "^GSPC", "name": "标普500", "type": "yfinance", "tag": "v3"},
    "jp": {"code": "^N225", "name": "日经225", "type": "yfinance", "tag": "v3"},
    "uk": {"code": "^FTSE", "name": "FTSE100", "type": "yfinance", "tag": "v3"},
    "de": {"code": "^GDAXI", "name": "德国DAX", "type": "yfinance", "tag": "v3"},
    "hk": {"code": "^HSI", "name": "恒生", "type": "yfinance", "tag": "v3"},
    "vn": {"code": "E1VFVN30.VN", "name": "越南VN30", "type": "yfinance", "tag": "new"},
    "sg": {"code": "^STI", "name": "新加坡STI", "type": "yfinance", "tag": "new"},
    "kr": {"code": "^KS11", "name": "韩国KOSPI", "type": "yfinance", "tag": "new"},
}

SCHEME_LABELS = {
    "equal": "等权(股票内)",
    "risk_parity": "风险平价(股票内)",
    "min_variance": "最小方差(股票内)",
    "max_sharpe": "最大夏普(股票内)",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2017-09-01")
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--lookback", type=int, default=252)
    p.add_argument("--lower", type=float, default=0.21)
    p.add_argument("--upper", type=float, default=0.29)
    p.add_argument("--capital", type=float, default=1_000_000)
    return p.parse_args()


def load_expanded_prices(start: str, end: str) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    series: dict[str, pd.Series] = {}
    labels: dict[str, str] = {}

    for key, meta in EXPANDED_STOCKS.items():
        if meta["type"] == "etf":
            cache = DATA_DIR / f"{meta['code']}.csv"
        else:
            cache = DATA_DIR / f"yf_{meta['code'].lstrip('^').replace('.', '_')}.csv"
        if cache.exists():
            part = pd.read_csv(cache, parse_dates=["date"])
        elif meta["type"] == "etf":
            part = _fetch_etf(meta["code"], start, end)
            part.to_csv(cache, index=False)
        else:
            part = _fetch_yfinance(meta["code"], start, end)
            part.to_csv(cache, index=False)
        part = part[(part["date"] >= pd.Timestamp(start)) & (part["date"] <= pd.Timestamp(end))]
        series[key] = part.set_index("date")["close"].rename(key)
        labels[key] = f"{meta['name']}({meta['code']})"

    for key, meta in MULTI_COUNTRY_OTHER.items():
        cache = DATA_DIR / f"{meta['code']}.csv"
        if cache.exists():
            part = pd.read_csv(cache, parse_dates=["date"])
        elif meta.get("type") == "xau_usd":
            from src.data import _fetch_xau_cny
            part = _fetch_xau_cny(start, end)
            part.to_csv(cache, index=False)
        else:
            part = _fetch_etf(meta["code"], start, end)
            part.to_csv(cache, index=False)
        part = part[(part["date"] >= pd.Timestamp(start)) & (part["date"] <= pd.Timestamp(end))]
        series[key] = part.set_index("date")["close"].rename(key)
        labels[key] = f"{meta['name']}({meta['code']})"

    stock_keys = list(EXPANDED_STOCKS.keys())
    cal = series["bond"].index
    prices = pd.DataFrame({k: series[k].reindex(cal).ffill() for k in series}).dropna(how="any")
    prices.index.name = "date"
    return prices, labels, stock_keys


def _equal_frac(n: int) -> np.ndarray:
    return np.full(n, 1.0 / n)


def _risk_parity_frac(hist: pd.DataFrame) -> np.ndarray:
    vol = hist.std() * np.sqrt(252)
    inv = 1.0 / vol.replace(0, np.nan)
    inv = inv.fillna(0.0)
    if inv.sum() <= 0:
        return _equal_frac(len(hist.columns))
    return (inv / inv.sum()).values


def _min_var_frac(hist: pd.DataFrame) -> np.ndarray:
    cov = hist.cov().values * 252
    n = cov.shape[0]

    def obj(w: np.ndarray) -> float:
        return float(w @ cov @ w)

    cons = {"type": "eq", "fun": lambda w: w.sum() - 1}
    bounds = [(0.0, 1.0)] * n
    x0 = _equal_frac(n)
    res = minimize(obj, x0, bounds=bounds, constraints=cons, method="SLSQP")
    return res.x if res.success else x0


def _max_sharpe_frac(hist: pd.DataFrame) -> np.ndarray:
    mu = hist.mean().values * 252
    cov = hist.cov().values * 252
    n = len(mu)

    def neg_sharpe(w: np.ndarray) -> float:
        ret = w @ mu
        vol = np.sqrt(w @ cov @ w)
        return -(ret / vol) if vol > 1e-12 else 0.0

    cons = {"type": "eq", "fun": lambda w: w.sum() - 1}
    bounds = [(0.0, 1.0)] * n
    x0 = _equal_frac(n)
    res = minimize(neg_sharpe, x0, bounds=bounds, constraints=cons, method="SLSQP")
    return res.x if res.success else x0


def make_stock_frac_fn(scheme: str):
    def fn(hist: pd.DataFrame) -> np.ndarray:
        if scheme == "equal":
            return _equal_frac(len(hist.columns))
        if scheme == "risk_parity":
            return _risk_parity_frac(hist)
        if scheme == "min_variance":
            return _min_var_frac(hist)
        if scheme == "max_sharpe":
            return _max_sharpe_frac(hist)
        raise ValueError(scheme)

    return fn


def plot_compare(summary: pd.DataFrame) -> Path:
    return plot_sharpe_drawdown_bars(
        summary,
        SCHEME_LABELS,
        "V4 扩展全球股票池 + 永久组合 (10国/区 + 债/货/金)",
        OUTPUT_DIR / "compare_sharpe_drawdown.png",
    )


def main() -> None:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prices, labels, stock_keys = load_expanded_prices(args.start, args.end)
    start = prices.index[0].date().isoformat()
    end = prices.index[-1].date().isoformat()
    n = len(stock_keys)

    rows = []
    for scheme in SCHEME_LABELS:
        config = GroupedBacktestConfig(
            stock_keys=stock_keys,
            lower_band=args.lower,
            upper_band=args.upper,
            initial_capital=args.capital,
        )
        if scheme == "equal":
            result = run_grouped_band_rebalance(prices, config)
        else:
            result = run_grouped_adaptive_stocks(
                prices, config, make_stock_frac_fn(scheme), lookback=args.lookback
            )
        perf = performance_summary(result.nav, scheme)
        rows.append(
            {
                "scheme": scheme,
                "label": SCHEME_LABELS[scheme],
                "sharpe": perf["sharpe"],
                "max_drawdown": perf["max_drawdown"],
                "cagr": perf["cagr"],
                "total_return": perf["total_return"],
                "rebalances": len(result.rebalance_log),
            }
        )
        result.nav.to_csv(OUTPUT_DIR / f"nav_{scheme}.csv", encoding="utf-8-sig")
        result.weights.resample("YE").last().to_csv(
            OUTPUT_DIR / f"year_end_weights_{scheme}.csv", encoding="utf-8-sig"
        )

    summary = pd.DataFrame(rows)
    summary.to_csv(OUTPUT_DIR / "performance_comparison.csv", index=False, encoding="utf-8-sig")
    chart = plot_compare(summary)

    with open(OUTPUT_DIR / "README.txt", "w", encoding="utf-8") as f:
        f.write("V4 扩展版永久组合\n")
        f.write(f"区间: {start} ~ {end}\n\n")
        f.write("股票池 25%（内部等权/优化），共10个:\n")
        for k, meta in EXPANDED_STOCKS.items():
            f.write(f"  [{meta['tag']}] {meta['name']} ({meta['code']})\n")
        f.write("\n其他各 25%: 十年国债 / 银华日利 / XAUUSD\n")
        f.write(f"四大类带宽: [{args.lower:.0%}, {args.upper:.0%}]\n")
        f.write("股票内部: 仅约束 sum=1、不做空，无单资产上下限\n")
        f.write("越南: E1VFVN30.VN (VN30 ETF 代理)\n")

    print("=" * 60)
    print("V4 扩展全球股票 + 永久组合 (夏普 / 回撤)")
    print("=" * 60)
    print(f"区间: {start} ~ {end}")
    print(f"股票 {n} 个，各目标 {0.25/n:.1%}（等权基准）+ 债/货/金 各 25%")
    print("\n股票池:")
    for k, meta in EXPANDED_STOCKS.items():
        print(f"  [{meta['tag']}] {labels[k]}")
    print("\n方案对比 (带宽再平衡 + 股票内部配权):")
    print(summary.to_string(index=False))
    print(f"\n图表: {chart}")
    print(f"目录: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
