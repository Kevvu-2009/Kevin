"""Persistence for OHLCV and data-quality runs (PostgreSQL via SQLAlchemy Core).

Uses parameterised Core statements (no ORM models needed) and an idempotent
UPSERT keyed on (exchange, symbol, timeframe, ts) so re-downloads never create
duplicates.  All functions take an explicit connection/engine to stay testable.
"""

from __future__ import annotations

import pandas as pd

from quantbot.data.quality import QualityReport


def upsert_ohlcv(df: pd.DataFrame, exchange: str, symbol: str, timeframe: str, engine=None) -> int:
    """Insert/replace OHLCV rows.  Returns rows written."""
    from sqlalchemy import text

    from quantbot.data.db import get_engine

    engine = engine or get_engine()
    if df.empty:
        return 0
    records = [
        {
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "ts": ts.to_pydatetime(),
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": float(r.volume),
        }
        for ts, r in df.iterrows()
    ]
    stmt = text(
        """
        INSERT INTO ohlcv (exchange, symbol, timeframe, ts, open, high, low, close, volume)
        VALUES (:exchange, :symbol, :timeframe, :ts, :open, :high, :low, :close, :volume)
        ON CONFLICT (exchange, symbol, timeframe, ts)
        DO UPDATE SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                      close=EXCLUDED.close, volume=EXCLUDED.volume
        """
    )
    with engine.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def load_ohlcv(
    exchange: str,
    symbol: str,
    timeframe: str,
    start=None,
    end=None,
    engine=None,
) -> pd.DataFrame:
    """Load OHLCV into a UTC-indexed DataFrame."""
    from sqlalchemy import text

    from quantbot.data.db import get_engine

    engine = engine or get_engine()
    clauses = ["exchange = :exchange", "symbol = :symbol", "timeframe = :timeframe"]
    params = {"exchange": exchange, "symbol": symbol, "timeframe": timeframe}
    if start is not None:
        clauses.append("ts >= :start")
        params["start"] = start
    if end is not None:
        clauses.append("ts < :end")
        params["end"] = end
    q = text(
        f"SELECT ts, open, high, low, close, volume FROM ohlcv "
        f"WHERE {' AND '.join(clauses)} ORDER BY ts ASC"
    )
    with engine.connect() as conn:
        df = pd.read_sql(q, conn, params=params, parse_dates=["ts"])
    if df.empty:
        return df
    return df.set_index("ts").astype(float)


def save_quality_run(report: QualityReport, exchange: str, symbol: str, engine=None) -> None:
    import json

    from sqlalchemy import text

    from quantbot.data.db import get_engine

    engine = engine or get_engine()
    stmt = text(
        """
        INSERT INTO data_quality_runs
            (exchange, symbol, timeframe, n_candles, n_gaps, n_duplicates, n_anomalies, passed, details)
        VALUES (:exchange, :symbol, :timeframe, :n_candles, :n_gaps, :n_duplicates,
                :n_anomalies, :passed, CAST(:details AS JSONB))
        """
    )
    with engine.begin() as conn:
        conn.execute(
            stmt,
            {
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": report.timeframe,
                "n_candles": report.n_candles,
                "n_gaps": report.n_gaps,
                "n_duplicates": report.n_duplicates,
                "n_anomalies": report.n_anomalies,
                "passed": report.passed,
                "details": json.dumps(report.to_dict()),
            },
        )
