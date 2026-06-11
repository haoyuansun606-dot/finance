"""Permanent portfolio with grouped equity sleeve (multi-country equal weight)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class GroupedBacktestConfig:
    stock_keys: list[str]
    other_keys: list[str] = field(default_factory=lambda: ["bond", "cash", "gold"])
    stock_sleeve: float = 0.25
    other_sleeve: float = 0.25
    lower_band: float = 0.21
    upper_band: float = 0.29
    initial_capital: float = 1_000_000.0
    transaction_cost: float = 0.0

    def target_weights(self) -> dict[str, float]:
        n = len(self.stock_keys)
        per_country = self.stock_sleeve / n
        weights = {k: per_country for k in self.stock_keys}
        for k in self.other_keys:
            weights[k] = self.other_sleeve
        return weights


@dataclass
class BacktestResult:
    nav: pd.Series
    weights: pd.DataFrame
    group_weights: pd.DataFrame
    rebalance_log: pd.DataFrame
    holdings_value: pd.DataFrame


def _apply_rebalance(values: np.ndarray, targets: np.ndarray, transaction_cost: float) -> tuple[np.ndarray, float]:
    total = values.sum()
    if total <= 0:
        return values, 0.0
    trades = targets * total - values
    cost = transaction_cost * np.abs(trades).sum()
    total_after = total - cost
    return targets * total_after, cost


def _group_weight(values: dict[str, float], stock_keys: list[str], other_keys: list[str]) -> dict[str, float]:
    total = sum(values.values())
    if total <= 0:
        return {}
    stock = sum(values[k] for k in stock_keys)
    out = {"stock": stock / total}
    for k in other_keys:
        out[k] = values[k] / total
    return out


def run_grouped_band_rebalance(prices: pd.DataFrame, config: GroupedBacktestConfig) -> BacktestResult:
    assets = list(prices.columns)
    stock_keys = config.stock_keys
    other_keys = config.other_keys
    target_map = config.target_weights()
    target_vec = np.array([target_map[a] for a in assets])

    dates = prices.index
    px = prices.to_numpy(dtype=float)
    shares = np.zeros(len(assets))
    shares[:] = (config.initial_capital * target_vec) / px[0]

    nav_list: list[float] = []
    weight_rows: list[np.ndarray] = []
    group_rows: list[dict] = []
    value_rows: list[np.ndarray] = []
    rebalance_rows: list[dict] = []

    for i, date in enumerate(dates):
        values_arr = shares * px[i]
        values = {assets[j]: values_arr[j] for j in range(len(assets))}
        total = values_arr.sum()
        weights = values_arr / total if total > 0 else target_vec
        groups = _group_weight(values, stock_keys, other_keys)

        if i > 0:
            breached = any(g <= config.lower_band + 1e-12 for g in groups.values()) or any(
                g >= config.upper_band - 1e-12 for g in groups.values()
            )
            if breached:
                new_values, cost = _apply_rebalance(values_arr, target_vec, config.transaction_cost)
                shares = np.where(px[i] > 0, new_values / px[i], 0.0)
                values_arr = shares * px[i]
                total = values_arr.sum()
                weights = values_arr / total
                groups = _group_weight({assets[j]: values_arr[j] for j in range(len(assets))}, stock_keys, other_keys)
                rebalance_rows.append(
                    {
                        "date": date,
                        "portfolio_value": total,
                        "transaction_cost": cost,
                        "group_stock": groups.get("stock"),
                        **{f"group_{k}": groups.get(k) for k in other_keys},
                    }
                )

        nav_list.append(total)
        weight_rows.append(weights.copy())
        group_rows.append(groups)
        value_rows.append(values_arr.copy())

    group_df = pd.DataFrame(group_rows, index=dates)
    group_df = group_df.rename(columns={"stock": "group_stock"})
    return BacktestResult(
        nav=pd.Series(nav_list, index=dates, name="nav"),
        weights=pd.DataFrame(weight_rows, index=dates, columns=assets),
        group_weights=group_df,
        rebalance_log=pd.DataFrame(rebalance_rows),
        holdings_value=pd.DataFrame(value_rows, index=dates, columns=assets),
    )


def run_grouped_band_rebalance_noon_delayed(
    prices: pd.DataFrame,
    config: GroupedBacktestConfig,
    rebalance_hours_gmt8: list[int] | None = None,
) -> BacktestResult:
    """
    Band breach detected at close does NOT trade immediately.
    Rebalance at GMT+8 scheduled hour on next eligible trading session (daily close as price proxy).
    """
    from schedule_rebalance import DEFAULT_REBALANCE_HOURS_GMT8, pick_rebalance_hour, scheduled_rebalance_due

    hours = rebalance_hours_gmt8 or DEFAULT_REBALANCE_HOURS_GMT8
    assets = list(prices.columns)
    stock_keys = config.stock_keys
    other_keys = config.other_keys
    target_map = config.target_weights()
    target_vec = np.array([target_map[a] for a in assets])

    dates = prices.index
    px = prices.to_numpy(dtype=float)
    shares = (config.initial_capital * target_vec) / px[0]

    nav_list: list[float] = []
    weight_rows: list[np.ndarray] = []
    group_rows: list[dict] = []
    value_rows: list[np.ndarray] = []
    rebalance_rows: list[dict] = []
    pending = False

    for i, date in enumerate(dates):
        values_arr = shares * px[i]

        if scheduled_rebalance_due(pending, date, dates, hours):
            new_values, cost = _apply_rebalance(values_arr, target_vec, config.transaction_cost)
            shares = np.where(px[i] > 0, new_values / px[i], 0.0)
            values_arr = shares * px[i]
            hour = pick_rebalance_hour(date, hours)
            rebalance_rows.append(
                {
                    "date": date,
                    "portfolio_value": values_arr.sum(),
                    "transaction_cost": cost,
                    "scheduled_hour_gmt8": hour,
                    "trigger": "band_pending",
                }
            )
            pending = False

        total = values_arr.sum()
        groups = _group_weight({assets[j]: values_arr[j] for j in range(len(assets))}, stock_keys, other_keys)

        if i > 0:
            breached = any(g <= config.lower_band + 1e-12 for g in groups.values()) or any(
                g >= config.upper_band - 1e-12 for g in groups.values()
            )
            if breached:
                pending = True

        weights = values_arr / total if total > 0 else target_vec
        nav_list.append(total)
        weight_rows.append(weights.copy())
        group_rows.append(groups)
        value_rows.append(values_arr.copy())

    group_df = pd.DataFrame(group_rows, index=dates)
    group_df = group_df.rename(columns={"stock": "group_stock"})
    return BacktestResult(
        nav=pd.Series(nav_list, index=dates, name="nav"),
        weights=pd.DataFrame(weight_rows, index=dates, columns=assets),
        group_weights=group_df,
        rebalance_log=pd.DataFrame(rebalance_rows),
        holdings_value=pd.DataFrame(value_rows, index=dates, columns=assets),
    )


def run_grouped_buy_and_hold(prices: pd.DataFrame, config: GroupedBacktestConfig) -> pd.Series:
    assets = list(prices.columns)
    target_map = config.target_weights()
    target_vec = np.array([target_map[a] for a in assets])
    px = prices.to_numpy(dtype=float)
    shares = (config.initial_capital * target_vec) / px[0]
    return pd.Series((shares * px).sum(axis=1), index=prices.index, name="nav")


def run_grouped_calendar_rebalance(prices: pd.DataFrame, config: GroupedBacktestConfig, freq: str = "YE") -> BacktestResult:
    assets = list(prices.columns)
    stock_keys = config.stock_keys
    other_keys = config.other_keys
    target_map = config.target_weights()
    target_vec = np.array([target_map[a] for a in assets])

    dates = prices.index
    px = prices.to_numpy(dtype=float)
    shares = (config.initial_capital * target_vec) / px[0]

    nav_list: list[float] = []
    weight_rows: list[np.ndarray] = []
    group_rows: list[dict] = []
    value_rows: list[np.ndarray] = []
    rebalance_rows: list[dict] = []

    rebalance_days = set(prices.groupby(pd.Grouper(freq=freq)).tail(1).index)

    for i, date in enumerate(dates):
        values_arr = shares * px[i]
        total = values_arr.sum()

        if i > 0 and date in rebalance_days:
            new_values, cost = _apply_rebalance(values_arr, target_vec, config.transaction_cost)
            shares = np.where(px[i] > 0, new_values / px[i], 0.0)
            values_arr = shares * px[i]
            total = values_arr.sum()
            groups = _group_weight({assets[j]: values_arr[j] for j in range(len(assets))}, stock_keys, other_keys)
            rebalance_rows.append(
                {"date": date, "portfolio_value": total, "transaction_cost": cost, "group_stock": groups.get("stock")}
            )
        else:
            groups = _group_weight({assets[j]: values_arr[j] for j in range(len(assets))}, stock_keys, other_keys)

        weights = values_arr / total if total > 0 else target_vec
        nav_list.append(total)
        weight_rows.append(weights.copy())
        group_rows.append(groups)
        value_rows.append(values_arr.copy())

    return BacktestResult(
        nav=pd.Series(nav_list, index=dates, name="nav"),
        weights=pd.DataFrame(weight_rows, index=dates, columns=assets),
        group_weights=pd.DataFrame(group_rows, index=dates),
        rebalance_log=pd.DataFrame(rebalance_rows),
        holdings_value=pd.DataFrame(value_rows, index=dates, columns=assets),
    )


def _build_target_vec(
    assets: list[str],
    stock_keys: list[str],
    other_keys: list[str],
    stock_sleeve: float,
    other_sleeve: float,
    stock_frac: np.ndarray,
) -> np.ndarray:
    """stock_frac sums to 1 over stock_keys."""
    weight_map: dict[str, float] = {}
    for k, frac in zip(stock_keys, stock_frac):
        weight_map[k] = stock_sleeve * frac
    for k in other_keys:
        weight_map[k] = other_sleeve
    return np.array([weight_map[a] for a in assets])


def run_grouped_adaptive_stocks(
    prices: pd.DataFrame,
    config: GroupedBacktestConfig,
    stock_frac_fn,
    lookback: int = 252,
) -> BacktestResult:
    """
    Permanent portfolio with 4-group band rebalance.
    Stock internal weights refresh monthly via stock_frac_fn(hist_returns) -> simplex.
    """
    assets = list(prices.columns)
    stock_keys = config.stock_keys
    other_keys = config.other_keys
    n_stock = len(stock_keys)
    stock_idx = [assets.index(k) for k in stock_keys]

    dates = prices.index
    px = prices.to_numpy(dtype=float)
    rets = prices.pct_change()

    month_starts = set(prices.groupby(pd.Grouper(freq="MS")).head(1).index)
    stock_frac = np.full(n_stock, 1.0 / n_stock)
    target_vec = _build_target_vec(assets, stock_keys, other_keys, config.stock_sleeve, config.other_sleeve, stock_frac)

    shares = (config.initial_capital * target_vec) / px[0]

    nav_list: list[float] = []
    weight_rows: list[np.ndarray] = []
    group_rows: list[dict] = []
    value_rows: list[np.ndarray] = []
    rebalance_rows: list[dict] = []

    for i, date in enumerate(dates):
        if i > 0 and date in month_starts and i >= lookback:
            hist = rets.iloc[i - lookback : i][stock_keys]
            if len(hist) >= 60:
                stock_frac = stock_frac_fn(hist)
                target_vec = _build_target_vec(
                    assets, stock_keys, other_keys, config.stock_sleeve, config.other_sleeve, stock_frac
                )
                values_arr = shares * px[i]
                total = values_arr.sum()
                shares = (total * target_vec) / px[i]

        values_arr = shares * px[i]
        total = values_arr.sum()
        groups = _group_weight({assets[j]: values_arr[j] for j in range(len(assets))}, stock_keys, other_keys)

        if i > 0:
            breached = any(g <= config.lower_band + 1e-12 for g in groups.values()) or any(
                g >= config.upper_band - 1e-12 for g in groups.values()
            )
            if breached:
                new_values, cost = _apply_rebalance(values_arr, target_vec, config.transaction_cost)
                shares = np.where(px[i] > 0, new_values / px[i], 0.0)
                values_arr = shares * px[i]
                total = values_arr.sum()
                groups = _group_weight({assets[j]: values_arr[j] for j in range(len(assets))}, stock_keys, other_keys)
                rebalance_rows.append(
                    {
                        "date": date,
                        "portfolio_value": total,
                        "transaction_cost": cost,
                        "group_stock": groups.get("stock"),
                    }
                )

        weights = values_arr / total if total > 0 else target_vec
        nav_list.append(total)
        weight_rows.append(weights.copy())
        group_rows.append(groups)
        value_rows.append(values_arr.copy())

    return BacktestResult(
        nav=pd.Series(nav_list, index=dates, name="nav"),
        weights=pd.DataFrame(weight_rows, index=dates, columns=assets),
        group_weights=pd.DataFrame(group_rows, index=dates),
        rebalance_log=pd.DataFrame(rebalance_rows),
        holdings_value=pd.DataFrame(value_rows, index=dates, columns=assets),
    )
