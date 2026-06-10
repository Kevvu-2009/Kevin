"""Live/paper trading loop driven by venue market data (Hyperliquid).

Wires together: YAML config -> venue (Hyperliquid or paper fills on live
Hyperliquid data) -> LiveEngine (risk + orders) -> polling bar-close loop.

Safety model
------------
* ``mode: paper``  — PaperBroker fills, REAL market data from Hyperliquid's
  public API (no credentials needed).  This is the mandatory pre-live stage.
* ``mode: live``   — requires BOTH the config and env ``QUANTBOT_MODE=live``
  (two independent switches), credentials, and — unless explicitly disabled —
  an existing discovery/validation report (we refuse to trade unvalidated).
* Consecutive-error circuit breaker: after N straight venue/data failures the
  runner flattens all positions (best-effort) and shuts down.
* The PortfolioRiskManager inside LiveEngine enforces loss limits and the
  drawdown kill switch on every bar.
"""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from quantbot.config import get_settings
from quantbot.config_files import load_yaml
from quantbot.logging_setup import get_logger
from quantbot.strategies.registry import get_strategy

log = get_logger("execution.live_runner")

_TF_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


@dataclass
class LiveRunnerConfig:
    symbols: list[str]
    timeframe: str = "4h"
    mode: str = "paper"                  # paper | live
    testnet: bool = True
    leverage: int = 1
    strategies: list[dict] = field(default_factory=list)
    poll_seconds: int = 30
    history_bars: int = 600
    max_consecutive_errors: int = 5
    require_validation_report: bool = True
    validation_report_dir: str = "reports/research"
    paper_equity: float = 10_000.0

    @classmethod
    def from_yaml(cls, path: str | Path) -> "LiveRunnerConfig":
        raw = load_yaml(path)
        venue = raw.get("venue", {})
        trading = raw.get("trading", {})
        safety = raw.get("safety", {})
        return cls(
            symbols=list(trading.get("symbols", [])),
            timeframe=str(trading.get("timeframe", "4h")),
            mode=str(raw.get("mode", "paper")).lower(),
            testnet=bool(venue.get("testnet", True)),
            leverage=int(trading.get("leverage", 1)),
            strategies=list(trading.get("strategies", [])),
            poll_seconds=int(trading.get("poll_seconds", 30)),
            max_consecutive_errors=int(safety.get("max_consecutive_errors", 5)),
            require_validation_report=bool(safety.get("require_validation_report", True)),
        )


class LiveRunner:
    def __init__(self, cfg: LiveRunnerConfig) -> None:
        self.cfg = cfg
        self.settings = get_settings()
        self._stop = False
        self._consecutive_errors = 0
        self._last_bar: dict[str, pd.Timestamp] = {}

        self._preflight()
        self.data_venue = self._build_data_venue()
        self.trade_venue = self._build_trade_venue()
        self.engine = self._build_engine()

    # ------------------------------------------------------------- preflight
    def _preflight(self) -> None:
        if not self.cfg.symbols:
            raise SystemExit("live runner: no symbols configured")
        if not self.cfg.strategies:
            raise SystemExit("live runner: no strategies configured")
        if self.cfg.mode == "live":
            if self.settings.mode != "live":
                raise SystemExit(
                    "config requests live mode but QUANTBOT_MODE != 'live' — "
                    "both switches must be set intentionally"
                )
            if self.cfg.require_validation_report:
                marker = Path(self.cfg.validation_report_dir) / "summary.json"
                if not marker.exists():
                    raise SystemExit(
                        f"live mode refused: no validation report at {marker}. "
                        "Run discovery + validation first (docs/RESEARCH_WORKFLOW.md), "
                        "or set safety.require_validation_report: false (NOT recommended)."
                    )
        log.info("live_runner_preflight_ok", mode=self.cfg.mode,
                 testnet=self.cfg.testnet, symbols=self.cfg.symbols)

    # ---------------------------------------------------------------- wiring
    def _build_data_venue(self):
        from quantbot.integrations.hyperliquid import HyperliquidVenue

        # Public data needs no credentials.
        return HyperliquidVenue(testnet=self.cfg.testnet)

    def _build_trade_venue(self):
        if self.cfg.mode == "live":
            from quantbot.integrations.hyperliquid import HyperliquidVenue

            venue = HyperliquidVenue(testnet=self.cfg.testnet)
            venue.authenticate()
            for sym in self.cfg.symbols:
                try:
                    venue.set_leverage(sym, self.cfg.leverage, is_cross=True)
                except Exception as e:
                    log.warning("leverage_set_failed", symbol=sym, error=str(e))
            return venue
        from quantbot.execution.paper_broker import PaperBroker

        return PaperBroker(starting_cash=self.cfg.paper_equity, costs=self.settings.costs)

    def _build_engine(self):
        from quantbot.execution.engine import LiveEngine

        spec = self.cfg.strategies[0]
        strategies = {
            sym: get_strategy(spec["name"], **(spec.get("params") or {}))
            for sym in self.cfg.symbols
        }
        equity = self.cfg.paper_equity
        if self.cfg.mode == "live":
            balances = self.trade_venue.get_balances()
            equity = sum(b.total for b in balances) or equity
        return LiveEngine(self.trade_venue, strategies,
                          settings=self.settings, starting_equity=equity)

    # ------------------------------------------------------------------ loop
    def _fetch_history(self, symbol: str) -> pd.DataFrame:
        candles = self.data_venue.get_ohlcv(symbol, self.cfg.timeframe,
                                            limit=self.cfg.history_bars)
        if not candles:
            raise RuntimeError(f"no candles for {symbol}")
        df = pd.DataFrame(
            {
                "open": [c.open for c in candles],
                "high": [c.high for c in candles],
                "low": [c.low for c in candles],
                "close": [c.close for c in candles],
                "volume": [c.volume for c in candles],
            },
            index=pd.DatetimeIndex([c.ts for c in candles], tz="UTC"),
        )
        return df[~df.index.duplicated(keep="last")].sort_index()

    def _on_tick(self) -> None:
        tf_s = _TF_SECONDS.get(self.cfg.timeframe, 3600)
        for symbol in self.cfg.symbols:
            df = self._fetch_history(symbol)
            # Drop the (possibly) in-progress bar: only act on CLOSED bars.
            now = pd.Timestamp.now(tz="UTC")
            closed = df[df.index + pd.Timedelta(seconds=tf_s) <= now]
            if closed.empty:
                continue
            last = closed.index[-1]
            if self._last_bar.get(symbol) == last:
                continue  # no new bar yet
            self._last_bar[symbol] = last
            # Paper venue needs the live price for marks/fills.
            if hasattr(self.trade_venue, "set_price"):
                self.trade_venue.set_price(symbol, float(closed["close"].iloc[-1]))
            self.engine.on_bar(symbol, closed)
            log.info("bar_processed", symbol=symbol, bar=str(last),
                     equity=round(self.engine.equity, 2),
                     positions=len(self.engine.positions))

    def run(self) -> int:
        signal.signal(signal.SIGINT, self._handle_stop)
        signal.signal(signal.SIGTERM, self._handle_stop)
        log.info("live_runner_started", mode=self.cfg.mode,
                 timeframe=self.cfg.timeframe, poll_s=self.cfg.poll_seconds)
        while not self._stop:
            try:
                self._on_tick()
                self._consecutive_errors = 0
            except Exception as e:  # noqa: BLE001 - circuit breaker
                self._consecutive_errors += 1
                log.error("tick_error", error=str(e)[:300],
                          consecutive=self._consecutive_errors)
                if self._consecutive_errors >= self.cfg.max_consecutive_errors:
                    log.error("circuit_breaker_tripped",
                              n=self._consecutive_errors)
                    self._emergency_shutdown()
                    return 2
            time.sleep(self.cfg.poll_seconds)
        log.info("live_runner_stopped")
        return 0

    # ---------------------------------------------------------------- safety
    def _handle_stop(self, signum, frame) -> None:  # pragma: no cover - signals
        log.info("shutdown_signal", signum=signum)
        self._stop = True

    def _emergency_shutdown(self) -> None:
        """Best-effort flatten + halt (kill switch / error cascade)."""
        try:
            self.engine.flatten_all(reason="emergency_shutdown")
        except Exception as e:  # pragma: no cover
            log.error("emergency_flatten_failed", error=str(e)[:300])
        self._stop = True


def run_from_config(path: str | Path) -> int:
    cfg = LiveRunnerConfig.from_yaml(path)
    return LiveRunner(cfg).run()
