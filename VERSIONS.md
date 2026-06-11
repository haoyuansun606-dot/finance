# Version Source Map

This file records how this repository was assembled from the original `permanent_portfolio/output` folders.

| Item | Source output | Source code basis |
| --- | --- | --- |
| `versions/main_compare.py` | `output/main_compare` | `main.py` |
| `versions/export_v1_v3.py` | `output/v1_cn`, `output/v2_global`, `output/v3_multicountry` | original `export_versions.py` notebook script |
| `versions/run_cn_backtest.py` | `output/cn` | original `run_cn_backtest.py` notebook script |
| `versions/run_global_backtest.py` | `output/global` | wrapper around original `run_cn_backtest.py --preset global` |
| `versions/run_multi_country.py` | `output/multicountry` | original `run_multi_country.py` notebook script |
| `versions/visualize_bands.py` | `output/visualizations` | original `visualize_bands.py` notebook script |
| `versions/v4_extended.py` | `output/v4_extended` | original `expanded_study.py` notebook script |
| `versions/v4_equal_low_corr.py` | `output/v4_equal_low_corr`, `output/v4_equal_low_corr_2014` | original `run_diversified_v4.py` notebook script |
| `versions/v4_equal_low_corr_cash_split.py` | `output/v4_low_corr_cash_proxy` | original `backtest_diversified_cash_split.py` notebook script |
| `versions/v4_equal_low_corr_us_tbond.py` | `output/v4_low_corr_us_tbond` | original `backtest_diversified_us_tbond.py` notebook script |
| `versions/snapshots/v4_equal_low_corr` | `output/v4_equal_low_corr/src` | frozen source snapshot |
| `versions/snapshots/v4_equal_low_corr_2014` | `output/v4_equal_low_corr_2014/src` | frozen source snapshot |
| `versions/snapshots/v4_equal_low_corr_cash_split` | `output/v4_low_corr_cash_proxy/src` | frozen source snapshot |
| `versions/snapshots/v4_equal_low_corr_us_tbond` | `output/v4_low_corr_us_tbond/src` | frozen source snapshot |
