"""Market data fetchers (akshare, yfinance)."""

from __future__ import annotations

import akshare as ak
import pandas as pd

from src.data.presets import DATA_DIR


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
