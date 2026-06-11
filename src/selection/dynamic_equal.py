"""Dynamic equal-weight selection with correlation filter."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.correlation_filter import select_stock_universe
from src.data import (
    BOND_ETF_SPLICE_DATE,
    DATA_DIR,
    MULTI_COUNTRY_OTHER,
    _fetch_xau_cny,
    load_price_frame,
    load_spliced_bond_series,
    load_spliced_cash_series,
)
from src.expanded_study import EXPANDED_STOCKS
from src.schedule_rebalance import pick_rebalance_hour, scheduled_rebalance_due
from src.strategies.grouped import GroupedBacktestConfig, _apply_rebalance, _group_weight


def load_all_prices(
    start: str,
    end: str,
    bond_splice: bool = False,
) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    series: dict[str, pd.Series] = {}
    labels: dict[str, str] = {}
    for key, meta in EXPANDED_STOCKS.items():
        part = load_price_frame(meta, start, end)
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
                fresh = _fetch_xau_cny(start, end)
                part = (
                    pd.concat([part, fresh], ignore_index=True)
                    .drop_duplicates("date")
                    .sort_values("date")
                )
                part.to_csv(cache, index=False)
            part = part[(part["date"] >= pd.Timestamp(start)) & (part["date"] <= pd.Timestamp(end))]
        else:
            part = load_price_frame(meta, start, end)
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
) -> tuple[pd.Series, pd.DataFrame, list[dict], list[dict], dict | None]:
    """Reselect stock universe monthly; equal weight survivors; optional delayed band rebalance."""
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
    last_selection: dict | None = None
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
            last_selection = sel
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
    return nav, weights, selection_log, rebalance_log, last_selection
