"""Shared helpers for V4 low-correlation portfolio variants."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.metrics import format_summary_table, performance_summary, yearly_returns
from src.strategies.grouped import GroupedBacktestConfig


def make_v4_config(args, stock_keys: list[str]) -> GroupedBacktestConfig:
    return GroupedBacktestConfig(
        stock_keys=stock_keys,
        lower_band=args.lower,
        upper_band=args.upper,
        initial_capital=args.capital,
    )


def write_v4_outputs(
    out_dir: Path,
    nav: pd.Series,
    weights: pd.DataFrame,
    selection_log: list[dict],
    band_log: list[dict],
    performance_label: str,
) -> tuple[pd.DataFrame, dict]:
    perf = performance_summary(nav, performance_label)
    summary = format_summary_table([perf])
    summary.to_csv(out_dir / "performance_summary.csv", encoding="utf-8-sig")
    pd.DataFrame(selection_log).to_csv(out_dir / "selection_log.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(band_log).to_csv(out_dir / "band_rebalance_log.csv", index=False, encoding="utf-8-sig")
    weights.iloc[-1].to_csv(out_dir / "latest_weights.csv", encoding="utf-8-sig")
    yearly_returns(nav).to_frame("GMT8中午调仓").to_csv(
        out_dir / "yearly_returns.csv", encoding="utf-8-sig"
    )
    return summary, perf


def write_2014_2017_returns(out_dir: Path, nav: pd.Series) -> pd.Series | None:
    segment = nav.loc["2014-01-01":"2017-12-31"]
    if len(segment) < 2:
        return None
    yearly_segment = yearly_returns(segment).to_frame("GMT8中午调仓")
    perf = performance_summary(segment, "2014-2017")
    segment_row = pd.Series({"GMT8中午调仓": perf["cagr"]}, name="2014-2017年化")
    pd.concat([yearly_segment, segment_row.to_frame().T]).to_csv(
        out_dir / "yearly_returns_2014_2017.csv", encoding="utf-8-sig"
    )
    return pd.Series(perf)
