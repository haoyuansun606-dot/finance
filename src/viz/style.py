"""Matplotlib style configuration."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FONT_FAMILIES = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]


def configure_chinese_matplotlib() -> None:
    plt.rcParams["font.sans-serif"] = FONT_FAMILIES
    plt.rcParams["axes.unicode_minus"] = False
