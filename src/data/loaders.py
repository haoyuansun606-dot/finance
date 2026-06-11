"""High-level price loaders for backtests."""

from __future__ import annotations

import pandas as pd

from src.data.fetchers import _fetch_etf, _fetch_xau_cny, _fetch_yfinance
from src.data.presets import (
    DATA_DIR,
    DEFAULT_ASSETS,
    MULTI_COUNTRY_EQUITIES,
    MULTI_COUNTRY_OTHER,
)


def _load_series(
    key: str,
    meta: dict,
    start_date: str,
    end_date: str,
    use_cache: bool,
) -> pd.Series:
    cache_path = DATA_DIR / f"{meta['code']}.csv"
    asset_type = meta.get("type", "etf")

    if use_cache and cache_path.exists():
        part = pd.read_csv(cache_path, parse_dates=["date"])
    elif asset_type == "etf":
        part = _fetch_etf(meta["code"], start_date, end_date)
        part.to_csv(cache_path, index=False)
    elif asset_type == "xau_usd":
        part = _fetch_xau_cny(start_date, end_date)
        part.to_csv(cache_path, index=False)
    else:
        raise ValueError(f"Unsupported asset type: {asset_type}")

    part = part[(part["date"] >= pd.Timestamp(start_date)) & (part["date"] <= pd.Timestamp(end_date))]
    return part.set_index("date")["close"].rename(key)


def load_prices(
    start_date: str = "2017-01-01",
    end_date: str = "2025-12-31",
    assets: dict | None = None,
    use_cache: bool = True,
    calendar: str = "cn",
) -> pd.DataFrame:
    """
    Return a wide DataFrame indexed by date with one column per asset key.

    For mixed calendars (e.g. XAUUSD vs A-share ETFs), align to the CN ETF
    trading calendar and forward-fill missing global quotes.
    """
    assets = assets or DEFAULT_ASSETS
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    series_map: dict[str, pd.Series] = {}
    for key, meta in assets.items():
        series_map[key] = _load_series(key, meta, start_date, end_date, use_cache)

    etf_keys = [k for k, m in assets.items() if m.get("type", "etf") == "etf"]
    if calendar == "cn" and etf_keys:
        cal_index = series_map[etf_keys[0]].index
        for key in etf_keys[1:]:
            cal_index = cal_index.intersection(series_map[key].index)
        prices = pd.DataFrame({k: series_map[k].reindex(cal_index).ffill() for k in assets})
    else:
        prices = pd.concat(series_map.values(), axis=1)

    prices = prices.dropna()
    prices.index.name = "date"
    return prices


def asset_labels(assets: dict | None = None) -> dict[str, str]:
    assets = assets or DEFAULT_ASSETS
    return {key: f"{meta['name']}({meta['code']})" for key, meta in assets.items()}


def _load_yfinance_series(key: str, meta: dict, start_date: str, end_date: str, use_cache: bool) -> pd.Series:
    cache_path = DATA_DIR / f"yf_{meta['code'].replace('^', '')}.csv"
    if use_cache and cache_path.exists():
        part = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        part = _fetch_yfinance(meta["code"], start_date, end_date)
        part.to_csv(cache_path, index=False)
    part = part[(part["date"] >= pd.Timestamp(start_date)) & (part["date"] <= pd.Timestamp(end_date))]
    return part.set_index("date")["close"].rename(key)


def load_multi_country_prices(
    start_date: str = "2017-09-01",
    end_date: str = "2025-12-31",
    use_cache: bool = True,
) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    """
    Load equal-weight global equity indices + bond/cash/gold.

    Returns (prices, labels, stock_keys).
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    series_map: dict[str, pd.Series] = {}
    labels: dict[str, str] = {}

    for key, meta in MULTI_COUNTRY_EQUITIES.items():
        series_map[key] = _load_yfinance_series(key, meta, start_date, end_date, use_cache)
        labels[key] = f"{meta['name']}({meta['code']})"

    for key, meta in MULTI_COUNTRY_OTHER.items():
        series_map[key] = _load_series(key, meta, start_date, end_date, use_cache)
        labels[key] = f"{meta['name']}({meta['code']})"

    stock_keys = list(MULTI_COUNTRY_EQUITIES.keys())
    cal_index = series_map["bond"].index
    prices = pd.DataFrame({k: series_map[k].reindex(cal_index).ffill() for k in series_map})
    prices = prices.dropna(how="any")
    prices.index.name = "date"
    return prices, labels, stock_keys
