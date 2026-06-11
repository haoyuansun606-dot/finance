# Version Source Map

This file records how this repository was assembled from the original `permanent_portfolio/output` folders.

| Item | Source output | Source code basis |
| --- | --- | --- |
| `versions/main_compare.py` | `output/main_compare` | `main.py` |
| `versions/export_v1_v3.py` | `output/v1_cn`, `output/v2_global`, `output/v3_multicountry` | `notebooks/export_versions.py` |
| `versions/run_cn_backtest.py` | `output/cn` | `notebooks/run_cn_backtest.py` |
| `versions/run_global_backtest.py` | `output/global` | thin wrapper around `notebooks/run_cn_backtest.py --preset global` |
| `versions/run_multi_country.py` | `output/multicountry` | `notebooks/run_multi_country.py` |
| `versions/visualize_bands.py` | `output/visualizations` | `notebooks/visualize_bands.py` |
| `versions/v4_extended.py` | `output/v4_extended` | `notebooks/expanded_study.py` |
| `versions/v4_equal_low_corr.py` | `output/v4_equal_low_corr`, `output/v4_equal_low_corr_2014` | `notebooks/run_diversified_v4.py` |
| `versions/v4_equal_low_corr_cash_split.py` | `output/v4_equal_low_corr_修改货币基金` | `notebooks/backtest_diversified_cash_split.py` |
| `versions/v4_equal_low_corr_us_tbond.py` | `output/v4_equal_low_corr_美债` | `notebooks/backtest_diversified_us_tbond.py` |
| `versions/snapshots/v4_equal_low_corr` | `output/v4_equal_low_corr/src` | frozen source snapshot |
| `versions/snapshots/v4_equal_low_corr_2014` | `output/v4_equal_low_corr_2014/src` | frozen source snapshot |
| `versions/snapshots/v4_equal_low_corr_cash_split` | `output/v4_equal_low_corr_修改货币基金/src` | frozen source snapshot |
| `versions/snapshots/v4_equal_low_corr_us_tbond` | `output/v4_equal_low_corr_美债/src` | frozen source snapshot |
