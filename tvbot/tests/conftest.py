"""Shared fixtures.

The mocked exchange is ``PaperExchange`` from the application itself, not a
bespoke test double, so the tests exercise the same object that backs DRY_RUN
mode in production.
"""

from __future__ import annotations

import time

import pytest

from app.config import Mode, Settings
from app.engine import Engine
from app.exchange import PaperExchange
from app.models import WebhookPayload
from app.notify import Notifier
from app.reconcile import Reconciler
from app.risk import RiskManager
from app.sizing import MarketSpec
from app.state import Store

BTC = "BTC/USDT:USDT"
ETH = "ETH/USDT:USDT"
SECRET = "test-secret-that-is-long-enough"

# Geometry used by the default payload: risk 710.5, reward 2131.0 -> RR 2.9993,
# stop distance 1.1065% of entry (inside the 0.4%-3.0% regime gate).
ENTRY = 64210.5
STOP = 63500.0
TARGET = 66341.5


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        mode=Mode.DRY_RUN,
        webhook_secret=SECRET,
        ip_allowlist_enabled=False,
        db_path=str(tmp_path / "test.sqlite3"),
        halt_file=str(tmp_path / "HALT"),
        log_file="",
        # Zero timeout keeps the fill wait instantaneous; the paper exchange
        # decides fill behaviour, not the clock.
        entry_fill_timeout_sec=0,
        entry_poll_interval_sec=0.01,
        reconcile_interval_sec=1,
        dry_run_equity=10_000.0,
    )


@pytest.fixture
def specs() -> dict[str, MarketSpec]:
    return {
        BTC: MarketSpec(BTC, amount_step=0.001, amount_min=0.001, price_step=0.1, min_notional=5.0),
        ETH: MarketSpec(ETH, amount_step=0.01, amount_min=0.01, price_step=0.01, min_notional=5.0),
    }


@pytest.fixture
def store(settings) -> Store:
    s = Store(settings.db_path)
    yield s
    s.close()


@pytest.fixture
def paper(settings, specs) -> PaperExchange:
    ex = PaperExchange(settings, equity=10_000.0, specs=specs)
    ex.set_price(BTC, ENTRY)
    ex.set_price(ETH, 3_000.0)
    return ex


@pytest.fixture
def notifier(settings) -> Notifier:
    return Notifier(settings)


@pytest.fixture
def risk(settings, store) -> RiskManager:
    return RiskManager(settings, store)


@pytest.fixture
def engine(settings, paper, store, risk, notifier) -> Engine:
    return Engine(settings, paper, store, risk, notifier)


@pytest.fixture
def reconciler(settings, paper, store, notifier) -> Reconciler:
    return Reconciler(settings, paper, store, notifier)


@pytest.fixture
def make_payload():
    """Build a valid payload, overridable field by field."""

    def _make(**overrides) -> WebhookPayload:
        now_ms = int(time.time() * 1000)
        bar_close = overrides.pop("bar_close_time", now_ms - 2_000)
        base: dict = {
            "secret": SECRET,
            "signal_id": "BTCUSDT.P-60-1730812800000",
            "action": "entry",
            "side": "long",
            "symbol": "BTCUSDT.P",
            "entry": ENTRY,
            "stop": STOP,
            "target": TARGET,
            "timeframe": "60",
            "bar_time": (bar_close - 3_600_000) if bar_close is not None else now_ms,
            "bar_close_time": bar_close,
        }
        base.update(overrides)
        return WebhookPayload.model_validate(base)

    return _make
