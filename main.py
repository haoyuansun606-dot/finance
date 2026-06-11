"""Unified runner for the permanent portfolio versions."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

VERSIONS: dict[str, list[str]] = {
    "main-compare": ["versions/main_compare.py"],
    "v1-v3": ["versions/export_v1_v3.py"],
    "cn": ["versions/run_cn_backtest.py"],
    "global": ["versions/run_global_backtest.py"],
    "multi-country": ["versions/run_multi_country.py"],
    "visualizations": ["versions/visualize_bands.py"],
    "v4-extended": ["versions/v4_extended.py"],
    "v4-low-corr": ["versions/v4_equal_low_corr.py"],
    "v4-low-corr-2014": ["versions/v4_equal_low_corr.py", "--bond-splice"],
    "v4-cash-split": ["versions/v4_equal_low_corr_cash_split.py"],
    "v4-us-tbond": ["versions/v4_equal_low_corr_us_tbond.py"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run permanent portfolio versions.")
    parser.add_argument(
        "version",
        nargs="?",
        choices=sorted(VERSIONS),
        help="Version key to run. Omit to list available versions.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available version keys.",
    )
    parser.add_argument(
        "extra_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the selected version script. Use -- before them.",
    )
    return parser.parse_args()


def list_versions() -> None:
    print("Available versions:")
    for key in sorted(VERSIONS):
        script = " ".join(VERSIONS[key])
        print(f"  {key:<18} {script}")


def main() -> int:
    args = parse_args()
    if args.list or not args.version:
        list_versions()
        return 0

    command = [sys.executable, *VERSIONS[args.version]]
    if args.extra_args:
        command.extend(args.extra_args[1:] if args.extra_args[0] == "--" else args.extra_args)

    print("Run:", " ".join(command))
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
