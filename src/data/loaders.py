"""High-level price loaders for backtests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.fetchers import _fetch_etf, _fetch_xau_cny, _fetch_yfinance
from src.data.presets import (
    DATA_DIR,
    DEFAULT_ASSETS,
    MULTI_COUNTRY_EQUITIES,
    MULTI_COUNTRY_OTHER,
)


def cache_path_for_asset(meta: dict) -> Path:
    asset_type = meta.get("type", "etf")
    if asset_type in {"etf", "xau_usd"}:
        return DATA_DIR / f"{meta['code']}.csv"
    code = meta["code"].lstrip("^").replace(".", "_")
    return DATA_DIR / f"yf_{code}.csv"


def fetch_price_frame(meta: dict, start_date: str, end_date: str) -> pd.DataFrame:
    asset_type = meta.get("type", "etf")
    try:
        if asset_type == "etf":
            return _fetch_etf(meta["code"], start_date, end_date)
        if asset_type == "xau_usd":
            return _fetch_xau_cny(start_date, end_date)
        return _fetch_yfinance(meta["code"], start_date, end_date)
    except Exception:
        fallback = meta.get("yf_fallback")
        if fallback:
            return _fetch_yfinance(fallback, start_date, end_date)
        raise


def load_price_frame(meta: dict, start_date: str, end_date: str, use_cache: bool = True) -> pd.DataFrame:
    """Load one asset price frame using cache, primary source, and optional yfinance fallback."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = cache_path_for_asset(meta)
    start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)

    if use_cache and cache.exists():
        part = pd.read_csv(cache, parse_dates=["date"])
        needs_refresh = part["date"].min() > start_ts or part["date"].max() < end_ts
        if needs_refresh:
            fresh = fetch_price_frame(meta, start_date, end_date)
            part = (
                pd.concat([part, fresh], ignore_index=True)
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date")
            )
            part.to_csv(cache, index=False)
    else:
        part = fetch_price_frame(meta, start_date, end_date)
        part.to_csv(cache, index=False)

    return part[(part["date"] >= start_ts) & (part["date"] <= end_ts)]


def _load_series(
    key: str,
    meta: dict,
    start_date: str,
    end_date: str,
    use_cache: bool,
) -> pd.Series:
    part = load_price_frame(meta, start_date, end_date, use_cache=use_cache)
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
