"""Asset presets and project paths."""

from __future__ import annotations

from pathlib import Path

DEFAULT_ASSETS = {
    "stock": {"code": "510300", "name": "沪深300ETF", "type": "etf"},
    "bond": {"code": "511260", "name": "十年国债ETF", "type": "etf"},
    "cash": {"code": "511880", "name": "银华日利(货基代理)", "type": "etf"},
    "gold": {"code": "518880", "name": "黄金ETF", "type": "etf"},
}

GLOBAL_ASSETS = {
    "stock": {"code": "513100", "name": "纳指100ETF", "type": "etf"},
    "bond": {"code": "511260", "name": "十年国债ETF", "type": "etf"},
    "cash": {"code": "511880", "name": "银华日利(货基代理)", "type": "etf"},
    "gold": {"code": "XAUUSD", "name": "XAUUSD(美元金价×USDCNH)", "type": "xau_usd"},
}

ASSET_PRESETS = {
    "cn": DEFAULT_ASSETS,
    "global": GLOBAL_ASSETS,
}

MULTI_COUNTRY_EQUITIES = {
    "us": {"code": "^GSPC", "name": "标普500"},
    "jp": {"code": "^N225", "name": "日经225"},
    "uk": {"code": "^FTSE", "name": "英国FTSE100"},
    "de": {"code": "^GDAXI", "name": "德国DAX"},
    "hk": {"code": "^HSI", "name": "恒生指数"},
}

MULTI_COUNTRY_OTHER = {
    "bond": {"code": "511260", "name": "十年国债ETF", "type": "etf"},
    "cash": {"code": "511880", "name": "银华日利(货基代理)", "type": "etf"},
    "gold": {"code": "XAUUSD", "name": "XAUUSD(美元金价×USDCNH)", "type": "xau_usd"},
}

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

BOND_ETF_CODE = "511260"
BOND_ETF_SPLICE_DATE = "2017-09-01"
