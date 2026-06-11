"""Run the global preset through the standard four-sleeve backtest."""

from __future__ import annotations

import sys

from run_cn_backtest import main


if "--preset" not in sys.argv:
    sys.argv.extend(["--preset", "global"])


if __name__ == "__main__":
    main()
