"""Visualization helpers (optional matplotlib dependency)."""

from src.viz.backtest import plot_backtest_comparison
from src.viz.correlation import plot_corr
from src.viz.heatmap import plot_yearly_heatmap
from src.viz.schemes import plot_sharpe_drawdown_bars
from src.viz.style import configure_chinese_matplotlib

__all__ = [
    "configure_chinese_matplotlib",
    "plot_backtest_comparison",
    "plot_corr",
    "plot_sharpe_drawdown_bars",
    "plot_yearly_heatmap",
]
