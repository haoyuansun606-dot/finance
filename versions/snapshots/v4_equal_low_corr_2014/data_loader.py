"""Fetch and cache ETF price data for the permanent portfolio backtest."""

from __future__ import annotations

from pathlib import Path

import akshare as ak
import pandas as pd

# Default proxies for the four sleeves (A-share ETFs)
DEFAULT_ASSETS = {
    "stock": {"code": "510300", "name": "沪深300ETF", "type": "etf"},
    "bond": {"code": "511260", "name": "十年国债ETF", "type": "etf"},
    "cash": {"code": "511880", "name": "银华日利(货基代理)", "type": "etf"},
    "gold": {"code": "518880", "name": "黄金ETF", "type": "etf"},
}

# Nasdaq ETF + XAUUSD converted to CNY
GLOBAL_ASSETS = {
    "stock": {"code": "513100", "name": "纳指100ETF", "type": "etf"},
    "bond": {"code": "511260", "name": "十年国债ETF", "type": "etf"},
    "cash": {"code": "511880", "name": "银华日利(货基代理)", "type": "etf"},
    "gold": {"code": "XAUUSD", "name": "XAUUSD(美元金价×USDCNH)", "type": "xau_usd"},
}

ASSET_PRESETS = {
    "cn": DEFAULT_ASSETS,
    "global": GLOBAL_ASSETS,
}

# Equal-weight global equities (yfinance) + bond/cash/gold from global preset
MULTI_COUNTRY_EQUITIES = {
    "us": {"code": "^GSPC", "name": "标普500"},
    "jp": {"code": "^N225", "name": "日经225"},
    "uk": {"code": "^FTSE", "name": "英国FTSE100"},
    "de": {"code": "^GDAXI", "name": "德国DAX"},
    "hk": {"code": "^HSI", "name": "恒生指数"},
}

MULTI_COUNTRY_OTHER = {
    "bond": {"code": "511260", "name": "十年国债ETF", "type": "etf"},
    "cash": {"code": "511880", "name": "银华日利(货基代理)", "type": "etf"},
    "gold": {"code": "XAUUSD", "name": "XAUUSD(美元金价×USDCNH)", "type": "xau_usd"},
}

DATA_DIR = Path(__file__).resolve().parent / "data"

# 511260 上市前用中债国债总指数；该日（含）起切换为十年国债 ETF
BOND_ETF_CODE = "511260"
BOND_ETF_SPLICE_DATE = "2017-09-01"


def _fetch_bond_treasury_index(start_date: str, end_date: str) -> pd.DataFrame:
    """中债国债总指数 (akshare bond_treasury_index_cbond), daily level."""
    cache_path = DATA_DIR / "cb_treasury_index.csv"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        part = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        df = ak.bond_treasury_index_cbond()
        part = df.rename(columns={"value": "close"})[["date", "close"]]
        part["date"] = pd.to_datetime(part["date"])
        part.to_csv(cache_path, index=False)
    part["date"] = pd.to_datetime(part["date"])
    mask = (part["date"] >= pd.Timestamp(start_date)) & (part["date"] <= pd.Timestamp(end_date))
    return part.loc[mask].sort_values("date").reset_index(drop=True)


def _fetch_shibor_cash_index(start_date: str, end_date: str) -> pd.DataFrame:
    """Synthetic cash sleeve from SHIBOR overnight, base 100."""
    cache_path = DATA_DIR / "shibor_onight_index.csv"
    if cache_path.exists():
        part = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        raw = ak.rate_interbank(
            market="上海银行同业拆借市场", symbol="Shibor人民币", indicator="隔夜"
        )
        raw["date"] = pd.to_datetime(raw["报告日"])
        raw = raw.sort_values("date")
        daily = raw["利率"].astype(float) / 100.0 / 252.0
        raw["close"] = (1.0 + daily).cumprod() * 100.0
        part = raw[["date", "close"]]
        part.to_csv(cache_path, index=False)
    mask = (part["date"] >= pd.Timestamp(start_date)) & (part["date"] <= pd.Timestamp(end_date))
    return part.loc[mask].sort_values("date").reset_index(drop=True)


def _rate_steps_to_index(dates: pd.DatetimeIndex, rate_table: list[tuple[str, float]], base: float = 100.0) -> pd.Series:
    """Benchmark rate steps → daily accrual total-return index."""
    table = sorted((pd.Timestamp(d), r) for d, r in rate_table)
    cur_rate = table[0][1]
    ti = 0
    level = base
    out: list[float] = []
    for d in dates:
        while ti + 1 < len(table) and d >= table[ti + 1][0]:
            ti += 1
            cur_rate = table[ti][1]
        out.append(level)
        level *= 1.0 + cur_rate / 100.0 / 252.0
    return pd.Series(out, index=dates)


def _fetch_cn_demand_deposit_index(start_date: str, end_date: str) -> pd.Series:
    """China demand-deposit benchmark (活期), base 100."""
    cache_path = DATA_DIR / "cn_demand_deposit_index.csv"
    start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)
    if cache_path.exists():
        part = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        cal = pd.DatetimeIndex(_fetch_bond_treasury_index("2000-01-01", end_date)["date"])
        rates = [
            ("2008-10-09", 0.72),
            ("2008-10-30", 0.36),
            ("2010-12-26", 0.40),
            ("2012-06-08", 0.35),
            ("2015-10-24", 0.35),
        ]
        part = pd.DataFrame({"date": cal, "close": _rate_steps_to_index(cal, rates).values})
        part.to_csv(cache_path, index=False)
    part = part[(part["date"] >= start_ts) & (part["date"] <= end_ts)]
    return part.set_index("date")["close"]


def _fetch_dubai_fixed_deposit_cny_index(start_date: str, end_date: str) -> pd.Series:
    """Dubai fixed deposit proxy: US 2Y yield accrual × USDCNH (AED≈USD)."""
    cache_path = DATA_DIR / "dubai_fixed_deposit_cny.csv"
    start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)
    if cache_path.exists():
        part = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        rates = ak.bond_zh_us_rate(start_date="20000101")
        rates["date"] = pd.to_datetime(rates["日期"])
        us2y = rates.set_index("date")["美国国债收益率2年"].astype(float) / 100.0
        fx = _fetch_usdcnh("2000-01-01", end_date).set_index("date")["usdcnh"]
        idx = pd.DatetimeIndex(us2y.index.union(fx.index)).sort_values().unique()
        y = us2y.reindex(idx).ffill()
        fx = fx.reindex(idx).ffill()
        usd_idx = 100.0
        cny_levels: list[float] = []
        for i, d in enumerate(idx):
            if i > 0:
                usd_idx *= 1.0 + float(y.iloc[i - 1]) / 252.0
            cny_levels.append(usd_idx * float(fx.loc[d]))
        part = pd.DataFrame({"date": idx, "close": cny_levels})
        part.to_csv(cache_path, index=False)
    part = part[(part["date"] >= start_ts) & (part["date"] <= end_ts)]
    return part.set_index("date")["close"]


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


def _fetch_us_treasury_bond_cny_index(start_date: str, end_date: str) -> pd.Series:
    """
    US Treasury bond sleeve in CNY: IEF (7-10Y US Treasury ETF, total return) × USDCNH.
    IEF 含票息与久期价格效应；USDCNH 反映人民币投资者汇率敞口。
    """
    cache_path = DATA_DIR / "us_treasury_ief_cny.csv"
    start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)
    if cache_path.exists():
        part = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        ief = _fetch_yfinance("IEF", "2002-01-01", end_date).set_index("date")["close"]
        fx = _fetch_usdcnh("2000-01-01", end_date).set_index("date")["usdcnh"]
        idx = ief.index.union(fx.index).sort_values()
        ief = ief.reindex(idx).ffill()
        fx = fx.reindex(idx).ffill()
        ok = ief.notna() & fx.notna()
        if not ok.any():
            raise RuntimeError("No overlap between IEF and USDCNH")
        d0 = idx[ok.argmax()]
        cny = (ief / ief.loc[d0]) * (fx / fx.loc[d0]) * 100.0
        part = cny.dropna().rename("close").reset_index()
        if part.empty:
            raise RuntimeError("Failed to build US Treasury IEF×USDCNH series")
        part.to_csv(cache_path, index=False)
    part = part[(part["date"] >= start_ts) & (part["date"] <= end_ts)]
    return part.set_index("date")["close"]


def load_us_treasury_bond_series(start_date: str, end_date: str) -> pd.Series:
    return _fetch_us_treasury_bond_cny_index(start_date, end_date).rename("bond")


def _fetch_etf(code: str, start_date: str, end_date: str, retries: int = 5) -> pd.DataFrame:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            df = ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="hfq",
            )
            df = df.rename(columns={"日期": "date", "收盘": "close"})
            df["date"] = pd.to_datetime(df["date"])
            return df[["date", "close"]].sort_values("date").reset_index(drop=True)
        except Exception as exc:
            last_err = exc
            if attempt + 1 < retries:
                import time

                time.sleep(2 + attempt)
    raise last_err  # type: ignore[misc]


def _fetch_xau_usd(start_date: str, end_date: str) -> pd.DataFrame:
    df = ak.futures_foreign_hist(symbol="XAU")
    df["date"] = pd.to_datetime(df["date"])
    out = df[["date", "close"]].rename(columns={"close": "xau_usd"})
    mask = (out["date"] >= pd.Timestamp(start_date)) & (out["date"] <= pd.Timestamp(end_date))
    return out.loc[mask].sort_values("date").reset_index(drop=True)


def _fetch_usdcnh(start_date: str, end_date: str) -> pd.DataFrame:
    cache_path = DATA_DIR / "usdcnh.csv"
    if cache_path.exists():
        out = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        try:
            df = ak.forex_hist_em(symbol="USDCNH")
            df["date"] = pd.to_datetime(df["日期"])
            out = df[["date", "最新价"]].rename(columns={"最新价": "usdcnh"})
        except Exception:
            for sym in ("CNH=X", "USDCNY=X"):
                try:
                    out = _fetch_yfinance(sym, start_date, end_date).rename(columns={"close": "usdcnh"})
                    if sym == "USDCNY=X":
                        out["usdcnh"] = 1.0 / out["usdcnh"]
                    break
                except Exception:
                    continue
            else:
                # Derive from cached XAUUSD / spot gold USD if available
                xau_cny = pd.read_csv(DATA_DIR / "XAUUSD.csv", parse_dates=["date"])
                xau = ak.futures_foreign_hist(symbol="XAU")
                xau["date"] = pd.to_datetime(xau["date"])
                merged = xau_cny.merge(
                    xau[["date", "close"]].rename(columns={"close": "xau_usd"}),
                    on="date",
                    how="inner",
                )
                merged["usdcnh"] = merged["close"] / merged["xau_usd"]
                out = merged[["date", "usdcnh"]]
        out.to_csv(cache_path, index=False)
    mask = (out["date"] >= pd.Timestamp(start_date)) & (out["date"] <= pd.Timestamp(end_date))
    return out.loc[mask].sort_values("date").reset_index(drop=True)


def _fetch_xau_cny(start_date: str, end_date: str) -> pd.DataFrame:
    """Spot gold in USD × USDCNH, expressed as a CNY notional price series."""
    xau = _fetch_xau_usd(start_date, end_date).set_index("date")["xau_usd"]
    fx = _fetch_usdcnh(start_date, end_date).set_index("date")["usdcnh"]
    combined = pd.concat([xau, fx], axis=1).sort_index().ffill().dropna()
    combined["close"] = combined["xau_usd"] * combined["usdcnh"]
    return combined[["close"]].reset_index()


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


def _fetch_yfinance(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    import yfinance as yf

    end_exclusive = (pd.Timestamp(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = yf.download(symbol, start=start_date, end=end_exclusive, auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError(f"No yfinance data for {symbol}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    out = df.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": "close"})
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    return out.sort_values("date").reset_index(drop=True)


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
