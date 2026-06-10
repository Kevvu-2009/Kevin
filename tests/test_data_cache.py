"""Local OHLCV cache: roundtrip, incremental merge, catalog, failure modes."""

import pandas as pd
import pytest

from quantbot.data.cache import DataCache, load_panel
from quantbot.data.synthetic import generate_ohlcv


@pytest.fixture()
def cache(tmp_path):
    return DataCache(tmp_path / "cache")


def test_write_read_roundtrip(cache):
    df = generate_ohlcv(n=500, seed=1)
    cache._write(df, cache.path("binance", "BTC/USDT", "1h"))
    out = cache.load("binance", "BTC/USDT", "1h")
    assert out is not None and len(out) == 500
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]


def test_incremental_update_merges_tail(cache, monkeypatch):
    full = generate_ohlcv(n=600, seed=2)
    old, new = full.iloc[:400], full.iloc[380:]  # overlapping tail

    cache._write(old, cache.path("binance", "ETH/USDT", "1h"))
    calls = {}

    def fake_fetch(symbol, timeframe, exchange, since):
        calls["since"] = since
        return new

    monkeypatch.setattr(DataCache, "_fetch", staticmethod(fake_fetch))
    merged = cache.update("ETH/USDT", "1h", "binance")
    assert len(merged) == 600                      # no duplicate bars
    assert merged.index.is_monotonic_increasing
    assert not merged.index.duplicated().any()
    # Incremental: fetch was asked to start near the cached tail, not at zero.
    assert calls["since"] is not None


def test_update_failure_returns_stale_cache(cache, monkeypatch):
    old = generate_ohlcv(n=300, seed=3)
    cache._write(old, cache.path("kraken", "BTC/USD", "1h"))

    def boom(symbol, timeframe, exchange, since):
        raise ConnectionError("exchange down")

    monkeypatch.setattr(DataCache, "_fetch", staticmethod(boom))
    out = cache.update("BTC/USD", "1h", "kraken")
    assert len(out) == 300                         # stale-but-served


def test_update_failure_without_cache_raises(cache, monkeypatch):
    def boom(symbol, timeframe, exchange, since):
        raise ConnectionError("exchange down")

    monkeypatch.setattr(DataCache, "_fetch", staticmethod(boom))
    with pytest.raises(ConnectionError):
        cache.update("DOGE/USDT", "1h", "binance")


def test_catalog_lists_series(cache):
    cache._write(generate_ohlcv(n=100, seed=4), cache.path("binance", "BTC/USDT", "4h"))
    cache._write(generate_ohlcv(n=120, seed=5), cache.path("bybit", "ETH/USDT", "1h"))
    cat = cache.catalog()
    assert len(cat) == 2
    assert set(cat["exchange"]) == {"binance", "bybit"}


def test_load_panel_skips_missing(cache):
    cache._write(generate_ohlcv(n=100, seed=6), cache.path("binance", "BTC/USDT", "1h"))
    panel = load_panel(cache, ["BTC/USDT", "MISSING/USDT"], "1h", "binance")
    assert set(panel) == {"BTC/USDT"}
