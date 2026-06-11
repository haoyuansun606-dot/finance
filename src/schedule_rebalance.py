"""GMT+8 scheduled rebalance helpers."""

from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd

TZ_CN = ZoneInfo("Asia/Shanghai")

# A-share regular session (GMT+8): 09:30 - 15:00
CN_SESSION_OPEN = time(9, 30)
CN_SESSION_CLOSE = time(15, 0)

# Fallback daytime hours (GMT+8) if 12:00 is not in session
DEFAULT_REBALANCE_HOURS_GMT8 = [12, 14, 10, 11, 13, 15, 9]


def is_weekday(ts: pd.Timestamp) -> bool:
    return ts.weekday() < 5


def is_cn_session_hour(ts: pd.Timestamp, hour: int) -> bool:
    """True if hour is within regular CN stock session (approx, whole hour)."""
    if not is_weekday(ts):
        return False
    t = time(hour, 0)
    # 12:00 and 14:00 are in session; 9:00 is before open -> treat 10+ as in session
    if hour == 9:
        return False
    return CN_SESSION_OPEN <= t <= CN_SESSION_CLOSE


def pick_rebalance_hour(ts: pd.Timestamp, hours: list[int] | None = None) -> int | None:
    """
    Pick first valid GMT+8 hour from priority list.
    On weekdays in session -> return hour; weekend -> None (defer).
    """
    hours = hours or DEFAULT_REBALANCE_HOURS_GMT8
    if not is_weekday(ts):
        return None
    for h in hours:
        if is_cn_session_hour(ts, h):
            return h
    return None


def scheduled_rebalance_due(
    pending: bool,
    date: pd.Timestamp,
    trading_index: pd.DatetimeIndex,
    hours: list[int] | None = None,
) -> bool:
    """
    Daily-bar proxy: if pending and `date` is a trading day with a valid session hour,
    execute rebalance on this date (represents noon GMT+8 on that session).
    """
    if not pending:
        return False
    if date not in trading_index:
        return False
    return pick_rebalance_hour(date, hours) is not None
