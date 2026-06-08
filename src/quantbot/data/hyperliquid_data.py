"""Public OHLCV download from Hyperliquid (no auth required).

Hyperliquid's ``candles_snapshot`` caps each response (~5000 candles), so this
paginates backwards/forwards and returns a clean UTC-indexed DataFrame matching
the rest of the data layer.  Use it to feed backtests / optimization with real
spot/perps data without a CEX or API key.

    from quantbot.data.hyperliquid_data import fetch_ohlcv_hyperliquid
    df = fetch_ohlcv_hyperliquid("BTC", "4h", since="2023-01-01")
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from quantbot.data.quality import clean_ohlcv
from quantbot.integrations.hyperliquid import _TF_MS, _INTERVALS, coin_of
from quantbot.logging_setup import get_logger

log = get_logger("data.hyperliquid")

_MAX_PER_CALL = 5000


def _to_ms(value) -> int:
    if isinstance(value, str):
        return int(pd.Timestamp(value, tz="UTC").timestamp() * 1000)
    if isinstance(value, datetime):
        return int(value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp() * 1000)
    return int(value)


def fetch_ohlcv_hyperliquid(
    symbol: str,
    timeframe: str = "1h",
    since: str | datetime | int | None = None,
    until: str | datetime | int | None = None,
    testnet: bool = False,
) -> pd.DataFrame:
    if timeframe not in _INTERVALS:
        raise ValueError(f"unsupported timeframe {timeframe}")

    from hyperliquid.info import Info
    from hyperliquid.utils import constants

    base = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
    info = Info(base, skip_ws=True)

    coin = coin_of(symbol)
    step = _TF_MS[timeframe]
    end_ms = _to_ms(until) if until is not None else int(time.time() * 1000)
    start_ms = _to_ms(since) if since is not None else end_ms - 730 * 86_400_000  # ~2y

    rows: list[dict] = []
    cursor = start_ms
    while cursor < end_ms:
        window_end = min(cursor + _MAX_PER_CALL * step, end_ms)
        batch = info.candles_snapshot(coin, _INTERVALS[timeframe], cursor, window_end)
        if not batch:
            break
        rows.extend(batch)
        last_t = int(batch[-1]["t"])
        if last_t < cursor:  # no forward progress
            break
        cursor = last_t + step
        time.sleep(0.2)  # be polite to the public endpoint

    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["t"].astype("int64"), unit="ms", utc=True)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df = df[["ts", "open", "high", "low", "close", "volume"]].set_index("ts")
    df = df.astype(float).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return clean_ohlcv(df)
