"""Spliced price series for bond/cash sleeves."""

from __future__ import annotations

import pandas as pd

from src.data.fetchers import (
    _fetch_bond_treasury_index,
    _fetch_cn_demand_deposit_index,
    _fetch_dubai_fixed_deposit_cny_index,
    _fetch_etf,
    _fetch_shibor_cash_index,
    _fetch_us_treasury_bond_cny_index,
    _fetch_yfinance,
)
from src.data.presets import BOND_ETF_CODE, BOND_ETF_SPLICE_DATE, DATA_DIR


def load_split_cash_series(
    start_date: str,
    end_date: str,
    demand_port_weight: float = 0.05,
    dubai_port_weight: float = 0.20,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    25% 现金仓内: 5% 活期 + 20% 迪拜定存 (占现金仓 20%:80%).
    合成价格 = 0.2×活期指数 + 0.8×迪拜定存指数 (首日均归一化为 100).
    """
    if abs(demand_port_weight + dubai_port_weight - 0.25) > 1e-9:
        raise ValueError("demand + dubai weights must sum to 0.25 (cash sleeve)")
    w_d = demand_port_weight / 0.25
    w_f = dubai_port_weight / 0.25
    demand = _fetch_cn_demand_deposit_index(start_date, end_date)
    dubai = _fetch_dubai_fixed_deposit_cny_index(start_date, end_date)
    cal = demand.index.union(dubai.index).sort_values()
    demand = demand.reindex(cal).ffill()
    dubai = dubai.reindex(cal).ffill()
    d0 = cal[0]
    demand = demand / demand.loc[d0] * 100.0
    dubai = dubai / dubai.loc[d0] * 100.0
    combined = w_d * demand + w_f * dubai
    return combined.rename("cash"), demand.rename("cash_demand"), dubai.rename("cash_dubai_fixed")


def load_spliced_cash_series(
    start_date: str,
    end_date: str,
    splice_date: str = BOND_ETF_SPLICE_DATE,
    use_cache: bool = True,
) -> pd.Series:
    """2017-09 前用 Shibor 隔夜合成指数，之后用 511880，拼接日水平对齐。"""
    splice_ts = pd.Timestamp(splice_date)
    shibor = _fetch_shibor_cash_index(start_date, end_date).set_index("date")["close"]

    etf_cache = DATA_DIR / "511880.csv"
    if use_cache and etf_cache.exists():
        etf_part = pd.read_csv(etf_cache, parse_dates=["date"])
    else:
        etf_part = _fetch_etf("511880", start_date, end_date)
        etf_part.to_csv(etf_cache, index=False)

    etf = etf_part[(etf_part["date"] >= splice_ts) & (etf_part["date"] <= pd.Timestamp(end_date))]
    etf = etf.set_index("date")["close"]
    if etf.empty:
        return shibor.rename("cash")

    etf_start = etf.index.min()
    s = shibor.reindex(shibor.index.union(pd.DatetimeIndex([etf_start]))).ffill()
    scale = float(etf.iloc[0] / s.loc[etf_start])
    before = s[s.index < etf_start] * scale
    spliced = pd.concat([before, etf]).sort_index()
    spliced = spliced[~spliced.index.duplicated(keep="last")]
    mask = (spliced.index >= pd.Timestamp(start_date)) & (spliced.index <= pd.Timestamp(end_date))
    return spliced.loc[mask].rename("cash")


def load_spliced_bond_series(
    start_date: str,
    end_date: str,
    splice_date: str = BOND_ETF_SPLICE_DATE,
    use_cache: bool = True,
) -> pd.Series:
    """
    2014–2017 段用中债国债总指数，2017-09 起切换 511260。
    在 splice_date 按水平对齐，保证拼接日价格连续。
    """
    splice_ts = pd.Timestamp(splice_date)
    treasury = _fetch_bond_treasury_index(start_date, end_date).set_index("date")["close"]

    etf_cache = DATA_DIR / f"{BOND_ETF_CODE}.csv"
    if use_cache and etf_cache.exists():
        etf_part = pd.read_csv(etf_cache, parse_dates=["date"])
        need_fetch = etf_part["date"].max() < pd.Timestamp(end_date) or etf_part["date"].min() > splice_ts
        if need_fetch:
            try:
                etf_part = _fetch_etf(BOND_ETF_CODE, start_date, end_date)
            except Exception:
                etf_part = _fetch_yfinance(f"{BOND_ETF_CODE}.SS", start_date, end_date)
            etf_part.to_csv(etf_cache, index=False)
    else:
        try:
            etf_part = _fetch_etf(BOND_ETF_CODE, start_date, end_date)
        except Exception:
            etf_part = _fetch_yfinance(f"{BOND_ETF_CODE}.SS", start_date, end_date)
        etf_part.to_csv(etf_cache, index=False)

    etf = etf_part[(etf_part["date"] >= splice_ts) & (etf_part["date"] <= pd.Timestamp(end_date))]
    etf = etf.set_index("date")["close"]
    if etf.empty:
        raise RuntimeError(f"No ETF data for {BOND_ETF_CODE} from {splice_date}")

    etf_start = etf.index.min()
    t = treasury.reindex(treasury.index.union(pd.DatetimeIndex([etf_start]))).ffill()
    scale = float(etf.iloc[0] / t.loc[etf_start])
    before = t[t.index < etf_start] * scale
    spliced = pd.concat([before, etf]).sort_index()
    spliced = spliced[~spliced.index.duplicated(keep="last")]
    mask = (spliced.index >= pd.Timestamp(start_date)) & (spliced.index <= pd.Timestamp(end_date))
    return spliced.loc[mask].rename("bond")


def load_us_treasury_bond_series(start_date: str, end_date: str) -> pd.Series:
    return _fetch_us_treasury_bond_cny_index(start_date, end_date).rename("bond")
