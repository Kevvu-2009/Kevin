"""Local OHLCV cache with incremental updates.

Layout: ``<root>/<exchange>/<SYMBOL>_<timeframe>.parquet`` (CSV fallback when
no parquet engine is installed).  ``update()`` downloads only bars newer than
the cached tail, so repeated research runs cost one small API call instead of
a full re-download.  All frames pass the data-quality cleaner on the way in
and a validation report on the way out.

Supported exchanges: any ccxt id with OHLCV (binance, bybit, kraken,
coinbase, okx, ...) — plus 'hyperliquid' via the native public info API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from quantbot.data.quality import clean_ohlcv, validate_ohlcv
from quantbot.logging_setup import get_logger

log = get_logger("data.cache")

_TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "-").replace(":", "_").upper()


class DataCache:
    def __init__(self, root: str | Path = "data_cache") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths
    def path(self, exchange: str, symbol: str, timeframe: str) -> Path:
        d = self.root / exchange.lower()
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{_safe_symbol(symbol)}_{timeframe}.parquet"

    # ------------------------------------------------------------------- io
    @staticmethod
    def _read(path: Path) -> pd.DataFrame | None:
        csv = path.with_suffix(".csv")
        try:
            if path.exists():
                return pd.read_parquet(path)
        except Exception:  # parquet engine missing/corrupt -> try csv
            pass
        if csv.exists():
            df = pd.read_csv(csv, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True)
            return df
        return None

    @staticmethod
    def _write(df: pd.DataFrame, path: Path) -> Path:
        try:
            df.to_parquet(path)
            return path
        except Exception:  # no pyarrow/fastparquet -> csv fallback
            csv = path.with_suffix(".csv")
            df.to_csv(csv)
            return csv

    # ----------------------------------------------------------------- load
    def load(self, exchange: str, symbol: str, timeframe: str) -> pd.DataFrame | None:
        df = self._read(self.path(exchange, symbol, timeframe))
        if df is None or df.empty:
            return None
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
        return df

    def catalog(self) -> pd.DataFrame:
        """Inventory of every cached series (exchange, symbol, span, bars)."""
        rows = []
        for f in sorted(self.root.glob("*/*")):
            if f.suffix not in (".parquet", ".csv"):
                continue
            df = self._read(f if f.suffix == ".parquet" else f.with_suffix(".parquet"))
            if df is None or df.empty:
                continue
            stem = f.stem
            sym, _, tf = stem.rpartition("_")
            rows.append(
                {
                    "exchange": f.parent.name,
                    "symbol": sym,
                    "timeframe": tf,
                    "bars": len(df),
                    "start": df.index[0],
                    "end": df.index[-1],
                }
            )
        return pd.DataFrame(rows)

    # --------------------------------------------------------------- update
    def update(
        self,
        symbol: str,
        timeframe: str = "1h",
        exchange: str = "binance",
        since: str | datetime | None = None,
        validate: bool = True,
    ) -> pd.DataFrame:
        """Fetch new bars since the cached tail (or ``since``) and merge.

        Returns the full merged frame.  API failures with a non-empty cache
        degrade gracefully: the stale cache is returned with a warning.
        """
        cached = self.load(exchange, symbol, timeframe)
        fetch_since: str | datetime | None = since
        if cached is not None and len(cached):
            overlap = timedelta(minutes=2 * _TF_MINUTES.get(timeframe, 60))
            fetch_since = (cached.index[-1].to_pydatetime() - overlap).replace(tzinfo=None)

        try:
            fresh = self._fetch(symbol, timeframe, exchange, fetch_since)
        except Exception as e:
            if cached is not None:
                log.warning("cache_update_failed_using_stale", symbol=symbol,
                            exchange=exchange, error=str(e), stale_end=str(cached.index[-1]))
                return cached
            raise

        merged = fresh if cached is None else pd.concat([cached, fresh])
        merged = merged.sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
        merged = clean_ohlcv(merged)
        if validate:
            report = validate_ohlcv(merged, timeframe)
            if not report.passed:
                log.warning("cache_quality_issues", symbol=symbol, issues=report.messages)

        written = self._write(merged, self.path(exchange, symbol, timeframe))
        log.info("cache_updated", symbol=symbol, exchange=exchange,
                 timeframe=timeframe, bars=len(merged), path=str(written))
        return merged

    def update_universe(
        self,
        symbols: list[str],
        timeframe: str = "1h",
        exchange: str = "binance",
        since: str | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Incrementally update every symbol; failures skip with a warning."""
        out: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            try:
                out[sym] = self.update(sym, timeframe, exchange, since)
            except Exception as e:
                log.warning("universe_symbol_failed", symbol=sym, error=str(e))
        return out

    # ---------------------------------------------------------------- fetch
    @staticmethod
    def _fetch(symbol: str, timeframe: str, exchange: str, since) -> pd.DataFrame:
        if exchange.lower() == "hyperliquid":
            from quantbot.data.hyperliquid_data import fetch_ohlcv_hyperliquid

            return fetch_ohlcv_hyperliquid(symbol, timeframe, since=since)
        from quantbot.data.downloader import fetch_ohlcv

        return fetch_ohlcv(symbol, timeframe, since=since, exchange_id=exchange.lower())


def load_panel(
    cache: DataCache,
    symbols: list[str],
    timeframe: str = "1h",
    exchange: str = "binance",
) -> dict[str, pd.DataFrame]:
    """Load a research panel from cache only (no network)."""
    panel: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = cache.load(exchange, sym, timeframe)
        if df is not None and len(df):
            panel[sym] = df
        else:
            log.warning("panel_symbol_missing", symbol=sym, exchange=exchange)
    return panel
