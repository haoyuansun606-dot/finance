"""Performance statistics for backtests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _max_drawdown(nav: pd.Series) -> float:
    peak = nav.cummax()
    dd = nav / peak - 1.0
    return float(dd.min())


def performance_summary(nav: pd.Series, name: str, periods_per_year: int = 252) -> dict:
    nav = nav.dropna()
    ret = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    total_return = nav.iloc[-1] / nav.iloc[0] - 1.0
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1.0 if years > 0 else np.nan
    vol = float(ret.std() * np.sqrt(periods_per_year))
    sharpe = float(ret.mean() / ret.std() * np.sqrt(periods_per_year)) if ret.std() > 0 else np.nan

    return {
        "strategy": name,
        "start": nav.index[0].date().isoformat(),
        "end": nav.index[-1].date().isoformat(),
        "total_return": total_return,
        "cagr": cagr,
        "annual_vol": vol,
        "sharpe": sharpe,
        "max_drawdown": _max_drawdown(nav),
        "final_nav": float(nav.iloc[-1]),
    }


def format_summary_table(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows).set_index("strategy")
    pct_cols = ["total_return", "cagr", "annual_vol", "max_drawdown"]
    for col in pct_cols:
        if col in df.columns:
            df[col] = (df[col] * 100).map(lambda x: f"{x:.2f}%")
    if "sharpe" in df.columns:
        df["sharpe"] = df["sharpe"].map(lambda x: f"{x:.2f}")
    if "final_nav" in df.columns:
        df["final_nav"] = df["final_nav"].map(lambda x: f"{x:,.0f}")
    return df


def yearly_returns(series: pd.Series) -> pd.Series:
    """Calendar-year return using first/last available quote in each year."""
    series = series.dropna()
    returns: dict[int, float] = {}
    for year in sorted(series.index.year.unique()):
        yr = series[series.index.year == year]
        if len(yr) >= 1:
            returns[year] = yr.iloc[-1] / yr.iloc[0] - 1.0
    return pd.Series(returns, name=series.name)


def yearly_returns_table(series_map: dict[str, pd.Series]) -> pd.DataFrame:
    """Rows = year, columns = series names."""
    parts = [yearly_returns(s).rename(name) for name, s in series_map.items()]
    df = pd.concat(parts, axis=1)
    df.index.name = "year"
    return df


def format_yearly_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        out[col] = out[col].map(lambda x: f"{x * 100:.2f}%" if pd.notna(x) else "-")
    return out
