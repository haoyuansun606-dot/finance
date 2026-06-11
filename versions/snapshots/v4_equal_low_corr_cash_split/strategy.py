"""Permanent portfolio backtest with band rebalancing."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestConfig:
    target_weight: float = 0.25
    lower_band: float = 0.15
    upper_band: float = 0.35
    initial_capital: float = 1_000_000.0
    transaction_cost: float = 0.0  # one-way cost as fraction of traded notional


@dataclass
class BacktestResult:
    nav: pd.Series
    weights: pd.DataFrame
    rebalance_log: pd.DataFrame
    holdings_value: pd.DataFrame


def _apply_rebalance(
    values: np.ndarray,
    target_weight: float,
    transaction_cost: float,
) -> tuple[np.ndarray, float]:
    total = values.sum()
    if total <= 0:
        return values, 0.0

    target_values = np.full_like(values, total * target_weight, dtype=float)
    trades = target_values - values
    cost = transaction_cost * np.abs(trades).sum()
    total_after_cost = total - cost
    return np.full_like(values, total_after_cost * target_weight, dtype=float), cost


def run_band_rebalance(prices: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
    """
    Daily mark-to-market backtest.

    At each close, if any sleeve weight <= lower_band or >= upper_band,
    rebalance all sleeves back to target_weight.
    """
    assets = list(prices.columns)
    n = len(assets)
    target = config.target_weight

    if not np.isclose(target * n, 1.0):
        raise ValueError("target_weight * number_of_assets must equal 1.0")

    dates = prices.index
    px = prices.to_numpy(dtype=float)
    shares = np.zeros(n, dtype=float)
    shares[:] = (config.initial_capital * target) / px[0]

    nav_list: list[float] = []
    weight_rows: list[np.ndarray] = []
    value_rows: list[np.ndarray] = []
    rebalance_rows: list[dict] = []

    for i, date in enumerate(dates):
        values = shares * px[i]
        total = values.sum()
        weights = values / total if total > 0 else np.full(n, target)

        if i > 0:
            breached = (weights <= config.lower_band + 1e-12).any() or (
                weights >= config.upper_band - 1e-12
            ).any()
            if breached:
                new_values, cost = _apply_rebalance(values, target, config.transaction_cost)
                shares = np.where(px[i] > 0, new_values / px[i], 0.0)
                values = shares * px[i]
                total = values.sum()
                weights = values / total if total > 0 else np.full(n, target)
                rebalance_rows.append(
                    {
                        "date": date,
                        "portfolio_value": total,
                        "transaction_cost": cost,
                        **{f"weight_{assets[j]}": weights[j] for j in range(n)},
                    }
                )

        nav_list.append(total)
        weight_rows.append(weights.copy())
        value_rows.append(values.copy())

    nav = pd.Series(nav_list, index=dates, name="nav")
    weights_df = pd.DataFrame(weight_rows, index=dates, columns=assets)
    values_df = pd.DataFrame(value_rows, index=dates, columns=assets)
    rebalance_df = pd.DataFrame(rebalance_rows)
    if not rebalance_df.empty:
        rebalance_df["date"] = pd.to_datetime(rebalance_df["date"])

    return BacktestResult(nav=nav, weights=weights_df, rebalance_log=rebalance_df, holdings_value=values_df)


def run_buy_and_hold(prices: pd.DataFrame, config: BacktestConfig) -> pd.Series:
    """Equal-weight buy at inception, never rebalance."""
    assets = list(prices.columns)
    n = len(assets)
    target = config.target_weight
    px = prices.to_numpy(dtype=float)
    shares = (config.initial_capital * target) / px[0]
    nav = pd.Series((shares * px).sum(axis=1), index=prices.index, name="nav")
    return nav


def run_calendar_rebalance(
    prices: pd.DataFrame,
    config: BacktestConfig,
    freq: str = "YE",
) -> BacktestResult:
    """Equal-weight with periodic rebalance (default: year-end)."""
    assets = list(prices.columns)
    n = len(assets)
    target = config.target_weight
    dates = prices.index
    px = prices.to_numpy(dtype=float)
    shares = np.zeros(n, dtype=float)
    shares[:] = (config.initial_capital * target) / px[0]

    nav_list: list[float] = []
    weight_rows: list[np.ndarray] = []
    value_rows: list[np.ndarray] = []
    rebalance_rows: list[dict] = []

    last_day_idx = prices.groupby(pd.Grouper(freq=freq)).tail(1).index
    rebalance_days = set(last_day_idx)

    for i, date in enumerate(dates):
        values = shares * px[i]
        total = values.sum()

        if i > 0 and date in rebalance_days:
            new_values, cost = _apply_rebalance(values, target, config.transaction_cost)
            shares = np.where(px[i] > 0, new_values / px[i], 0.0)
            values = shares * px[i]
            total = values.sum()
            weights = values / total
            rebalance_rows.append(
                {
                    "date": date,
                    "portfolio_value": total,
                    "transaction_cost": cost,
                    **{f"weight_{assets[j]}": weights[j] for j in range(n)},
                }
            )
        else:
            weights = values / total if total > 0 else np.full(n, target)

        nav_list.append(total)
        weight_rows.append(weights.copy())
        value_rows.append(values.copy())

    return BacktestResult(
        nav=pd.Series(nav_list, index=dates, name="nav"),
        weights=pd.DataFrame(weight_rows, index=dates, columns=assets),
        rebalance_log=pd.DataFrame(rebalance_rows),
        holdings_value=pd.DataFrame(value_rows, index=dates, columns=assets),
    )
