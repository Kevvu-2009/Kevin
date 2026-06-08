"""Historical OHLCV downloader via CCXT.

Handles pagination (CCXT returns at most ~1000 candles per call), rate-limit
backoff, and returns a tidy, validated DataFrame indexed by UTC timestamp.
CCXT is imported lazily so the rest of the package imports without it.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from quantbot.data.quality import clean_ohlcv
from quantbot.logging_setup import get_logger

log = get_logger("data.downloader")

_TF_MS = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def _make_exchange(exchange_id: str, api_key: str | None = None, secret: str | None = None):
    import ccxt

    klass = getattr(ccxt, exchange_id)
    cfg = {"enableRateLimit": True}
    if api_key:
        cfg["apiKey"] = api_key
    if secret:
        cfg["secret"] = secret
    return klass(cfg)


def fetch_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    since: datetime | str | None = None,
    until: datetime | None = None,
    exchange_id: str = "binance",
    limit: int = 1000,
    api_key: str | None = None,
    secret: str | None = None,
    max_retries: int = 4,
) -> pd.DataFrame:
    """Download OHLCV with pagination.

    Args:
        since: start (inclusive). datetime, ISO string, or None (=> ~2y back).
        until: end (exclusive). Defaults to now.
    """
    if timeframe not in _TF_MS:
        raise ValueError(f"Unsupported timeframe {timeframe}")
    ex = _make_exchange(exchange_id, api_key, secret)
    step = _TF_MS[timeframe]

    if since is None:
        since_ms = ex.milliseconds() - 730 * 86_400_000  # ~2 years
    elif isinstance(since, str):
        since_ms = ex.parse8601(since)
        if since_ms is None:
            # ex.parse8601 returns None for date-only / non-strict-ISO strings
            # (e.g. "2024-01-01"); fall back to pandas which is far more lenient.
            since_ms = int(pd.Timestamp(since, tz="UTC").timestamp() * 1000)
    else:
        since_ms = int(since.replace(tzinfo=timezone.utc).timestamp() * 1000)
    until_ms = (
        int(until.replace(tzinfo=timezone.utc).timestamp() * 1000)
        if until
        else ex.milliseconds()
    )

    rows: list[list] = []
    cursor = since_ms
    while cursor < until_ms:
        batch = _fetch_batch(ex, symbol, timeframe, cursor, limit, max_retries)
        if not batch:
            break
        rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= cursor:  # no progress, avoid infinite loop
            break
        cursor = last_ts + step
        time.sleep(ex.rateLimit / 1000.0)

    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset="ts")
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    df = df[df.index < pd.to_datetime(until_ms, unit="ms", utc=True)]
    return clean_ohlcv(df)


def _fetch_batch(ex, symbol, timeframe, since_ms, limit, max_retries) -> list:
    import ccxt

    for attempt in range(max_retries):
        try:
            return ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:  # pragma: no cover
            wait = 2 ** attempt
            log.warning("ohlcv_retry", attempt=attempt, wait=wait, error=str(e))
            time.sleep(wait)
        except ccxt.BaseError as e:  # pragma: no cover
            log.error("ohlcv_error", error=str(e))
            raise
    return []
