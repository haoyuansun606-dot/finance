"""Data loading package — fetch, splice, and assemble price panels."""

from src.data.fetchers import (
    _fetch_bond_treasury_index,
    _fetch_cn_demand_deposit_index,
    _fetch_dubai_fixed_deposit_cny_index,
    _fetch_etf,
    _fetch_shibor_cash_index,
    _fetch_us_treasury_bond_cny_index,
    _fetch_usdcnh,
    _fetch_xau_cny,
    _fetch_xau_usd,
    _fetch_yfinance,
    _rate_steps_to_index,
)
from src.data.loaders import (
    _load_series,
    _load_yfinance_series,
    asset_labels,
    load_multi_country_prices,
    load_prices,
)
from src.data.presets import (
    ASSET_PRESETS,
    BOND_ETF_CODE,
    BOND_ETF_SPLICE_DATE,
    DATA_DIR,
    DEFAULT_ASSETS,
    GLOBAL_ASSETS,
    MULTI_COUNTRY_EQUITIES,
    MULTI_COUNTRY_OTHER,
)
from src.data.splice import (
    load_split_cash_series,
    load_spliced_bond_series,
    load_spliced_cash_series,
    load_us_treasury_bond_series,
)

__all__ = [
    "ASSET_PRESETS",
    "BOND_ETF_CODE",
    "BOND_ETF_SPLICE_DATE",
    "DATA_DIR",
    "DEFAULT_ASSETS",
    "GLOBAL_ASSETS",
    "MULTI_COUNTRY_EQUITIES",
    "MULTI_COUNTRY_OTHER",
    "_fetch_bond_treasury_index",
    "_fetch_cn_demand_deposit_index",
    "_fetch_dubai_fixed_deposit_cny_index",
    "_fetch_etf",
    "_fetch_shibor_cash_index",
    "_fetch_us_treasury_bond_cny_index",
    "_fetch_usdcnh",
    "_fetch_xau_cny",
    "_fetch_xau_usd",
    "_fetch_yfinance",
    "_load_series",
    "_load_yfinance_series",
    "_rate_steps_to_index",
    "asset_labels",
    "load_multi_country_prices",
    "load_prices",
    "load_split_cash_series",
    "load_spliced_bond_series",
    "load_spliced_cash_series",
    "load_us_treasury_bond_series",
]
