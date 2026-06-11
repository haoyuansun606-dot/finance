# Permanent Portfolio

这个仓库整理了永久组合相关的回测脚本和历史版本。顶层 `main.py` 是统一入口，`versions/` 里保留不同版本的运行脚本，`versions/snapshots/` 里保存了从历史产出目录固化下来的 v4 版本源码，方便复现当时的结果。

## Quick Start

```bash
pip install -r requirements.txt
pip install -r requirements-viz.txt

python main.py --list
python main.py main-compare
python main.py v1-v3
python main.py v4-low-corr
python main.py v4-low-corr-2014
python main.py v4-cash-split
python main.py v4-us-tbond
```

结果默认写入 `output/`。行情数据默认缓存在 `data/`，首次运行可能需要联网下载。

## Versions

| Key | Output folder | Description | Script |
| --- | --- | --- | --- |
| `main-compare` | `output/main_compare` | 三策略一键对比：买入持有、年末再平衡、多国股指等权 | `versions/main_compare.py` |
| `v1-v3` | `output/v1_cn`, `output/v2_global`, `output/v3_multicountry` | V1 中国四资产、V2 纳指+XAUUSD、V3 五国股指等权 | `versions/export_v1_v3.py` |
| `cn` | `output/cn` | 中国四资产带宽、买入持有、年末再平衡对比 | `versions/run_cn_backtest.py` |
| `global` | `output/global` | 全球版四资产带宽、买入持有、年末再平衡对比 | `versions/run_global_backtest.py` |
| `multi-country` | `output/multicountry` | 五国股指等权永久组合 | `versions/run_multi_country.py` |
| `visualizations` | `output/visualizations` | 中国/全球 preset 的带宽和年度收益可视化图表 | `versions/visualize_bands.py` |
| `v4-extended` | `output/v4_extended` | 扩展 10 个国家/地区股票池，比较股票仓配权方案 | `versions/v4_extended.py` |
| `v4-low-corr` | `output/v4_equal_low_corr` | 等权 + 剔除高相关指数 + GMT+8 延迟调仓 | `versions/v4_equal_low_corr.py` |
| `v4-low-corr-2014` | `output/v4_equal_low_corr_2014` | 2014 起，债券和现金拼接版本 | `versions/v4_equal_low_corr.py --bond-splice` |
| `v4-cash-split` | `output/v4_equal_low_corr_修改货币基金` | 现金仓改为 5% 活期 + 20% 迪拜定存 proxy | `versions/v4_equal_low_corr_cash_split.py` |
| `v4-us-tbond` | `output/v4_equal_low_corr_美债` | 债券仓改为 IEF × USDCNH，美债人民币计价 | `versions/v4_equal_low_corr_us_tbond.py` |

## Repository Layout

```text
.
├── main.py
├── README.md
├── requirements.txt
├── requirements-viz.txt
├── src/                    # current shared code
├── versions/
│   ├── _bootstrap.py
│   ├── export_v1_v3.py
│   ├── main_compare.py
│   ├── run_cn_backtest.py
│   ├── run_global_backtest.py
│   ├── run_multi_country.py
│   ├── visualize_bands.py
│   ├── v4_extended.py
│   ├── v4_equal_low_corr.py
│   ├── v4_equal_low_corr_cash_split.py
│   ├── v4_equal_low_corr_us_tbond.py
│   └── snapshots/          # frozen source from output/*/src
└── output/                 # generated results, ignored by git except .gitkeep
```

## Notes

- `src/` 是当前共享库版本，适合继续开发。
- `versions/snapshots/` 是按历史产出版本固化的可运行源码，适合复现当时结果。
- `output/v4_asia` 在原项目 README 中标注为早期废弃试验，因此没有作为主入口；对应替代版本是 `v4-extended`。
