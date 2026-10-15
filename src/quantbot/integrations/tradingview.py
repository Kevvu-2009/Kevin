"""TradingView alert -> QuantBot bridge.

TradingView alerts can POST a JSON body to a webhook URL.  This module parses
that body, authenticates it with a shared secret, de-duplicates retries and
turns it into an entry / exit on the ``LiveEngine`` — so every TradingView
signal still goes through QuantBot's risk gate, position sizing, order retries
and kill switch.

Expected alert message (set in TradingView's alert "Message" box)::

    {
      "secret": "<TRADINGVIEW_WEBHOOK_SECRET>",
      "action": "{{strategy.order.action}}",   # buy | sell | close
      "symbol": "{{ticker}}",                   # BTCUSDT, BINANCE:BTCUSDT, BTC/USDT ...
      "price": {{close}},
      "stop": 61250.5,                          # optional, below price for a long
      "take_profit": 66000,                     # optional
      "strategy": "my_pine_strategy",           # optional, for logs
      "id": "{{timenow}}"                       # optional, used for de-duplication
    }

Like the rest of the engine this is long-only: ``buy`` opens a long and
``sell`` / ``close`` / ``exit`` / ``flat`` closes it.
"""

from __future__ import annotations

import hmac
import json
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from quantbot.logging_setup import get_logger, log_signal

log = get_logger("integrations.tradingview")

OPEN_ACTIONS = {"buy", "long", "enter_long"}
CLOSE_ACTIONS = {"sell", "close", "exit", "exit_long", "flat"}
_QUOTES = ("USDT", "USDC", "USD", "BUSD", "EUR")


class AlertError(ValueError):
    """The alert body is malformed or unauthorised."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def normalize_symbol(ticker: str) -> str:
    """Map TradingView tickers onto QuantBot's ``BASE/QUOTE`` form.

    ``BINANCE:BTCUSDT`` -> ``BTC/USDT``, ``BTCUSDT.P`` -> ``BTC/USDT``,
    ``ETH/USDC`` -> ``ETH/USDC``.  Unknown shapes are returned upper-cased.
    """
    t = ticker.strip().upper()
    if ":" in t:
        t = t.split(":", 1)[1]
    for suffix in (".P", "PERP", "-PERP"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    t = t.replace("-", "/")
    if "/" in t:
        return t
    for quote in _QUOTES:
        if t.endswith(quote) and len(t) > len(quote):
            return f"{t[: -len(quote)]}/{quote}"
    return t


def _opt_float(body: dict, key: str) -> float:
    raw = body.get(key)
    if raw in (None, ""):
        return float("nan")
    try:
        val = float(raw)
    except (TypeError, ValueError) as e:
        raise AlertError(f"'{key}' must be a number, got {raw!r}") from e
    if not math.isfinite(val) or val <= 0:
        raise AlertError(f"'{key}' must be a positive number, got {raw!r}")
    return val


@dataclass
class TradingViewAlert:
    action: str            # "open" | "close"
    symbol: str
    price: float           # NaN when the alert carried no price
    stop: float = float("nan")
    take_profit: float = float("nan")
    strategy: str = "tradingview"
    alert_id: str | None = None

    @classmethod
    def parse(cls, raw: bytes | str | dict, secret: str) -> TradingViewAlert:
        """Parse and authenticate an alert body.  Raises ``AlertError``."""
        if isinstance(raw, dict):
            body = raw
        else:
            try:
                body = json.loads(raw)
            except (ValueError, TypeError) as e:
                raise AlertError("alert body must be JSON") from e
        if not isinstance(body, dict):
            raise AlertError("alert body must be a JSON object")

        if not secret:
            raise AlertError("webhook secret not configured on the server", status=500)
        given = str(body.get("secret", ""))
        if not hmac.compare_digest(given.encode(), secret.encode()):
            raise AlertError("invalid secret", status=401)

        action_raw = str(body.get("action", "")).strip().lower()
        if action_raw in OPEN_ACTIONS:
            action = "open"
        elif action_raw in CLOSE_ACTIONS:
            action = "close"
        else:
            raise AlertError(f"unknown action {action_raw!r}; use buy, sell or close")

        ticker = str(body.get("symbol") or body.get("ticker") or "").strip()
        if not ticker:
            raise AlertError("missing 'symbol'")

        alert = cls(
            action=action,
            symbol=normalize_symbol(ticker),
            price=_opt_float(body, "price"),
            stop=_opt_float(body, "stop"),
            take_profit=_opt_float(body, "take_profit"),
            strategy=str(body.get("strategy") or "tradingview"),
            alert_id=str(body["id"]) if body.get("id") not in (None, "") else None,
        )
        if action == "open" and not math.isnan(alert.price):
            if not math.isnan(alert.stop) and alert.stop >= alert.price:
                raise AlertError("'stop' must be below 'price' for a long entry")
            if not math.isnan(alert.take_profit) and alert.take_profit <= alert.price:
                raise AlertError("'take_profit' must be above 'price' for a long entry")
        return alert

    def dedupe_key(self) -> str | None:
        if self.alert_id is None:
            return None
        return f"{self.symbol}|{self.action}|{self.alert_id}"


class TradingViewBridge:
    """Routes authenticated alerts into a ``LiveEngine``.

    Thread-safe: the webhook server may handle requests concurrently, so every
    alert is applied under one lock.
    """

    def __init__(self, engine: Any, secret: str, allowed_symbols: set[str] | None = None,
                 dedupe_size: int = 1000) -> None:
        if not secret:
            raise ValueError("TradingView webhook secret must be set")
        self.engine = engine
        self.secret = secret
        self.allowed_symbols = {normalize_symbol(s) for s in allowed_symbols} if allowed_symbols else None
        self._seen: OrderedDict[str, dict] = OrderedDict()
        self._dedupe_size = dedupe_size
        self._lock = threading.Lock()

    def handle(self, raw: bytes | str | dict) -> dict:
        """Process one webhook body; returns a JSON-able result dict."""
        alert = TradingViewAlert.parse(raw, self.secret)
        if self.allowed_symbols is not None and alert.symbol not in self.allowed_symbols:
            raise AlertError(f"symbol {alert.symbol} is not in the allowed list", status=403)

        with self._lock:
            key = alert.dedupe_key()
            if key is not None and key in self._seen:
                return {**self._seen[key], "duplicate": True}

            price = alert.price
            if math.isnan(price):
                try:
                    price = float(self.engine.venue.get_ticker(alert.symbol))
                except Exception as e:
                    raise AlertError(
                        f"alert has no 'price' and no live price for {alert.symbol}: {e}"
                    ) from e

            log_signal(log, symbol=alert.symbol, strategy=alert.strategy, price=price,
                       source="tradingview", action=alert.action)

            # Honour stops/take-profits on the current price first.
            exited = self.engine.check_exits(alert.symbol, price)
            if alert.action == "open":
                status = self.engine.open_position(
                    alert.symbol, alert.strategy, price, alert.stop, alert.take_profit
                )
            else:
                status = exited or self.engine.close_position(alert.symbol, price, reason="tradingview")

            result = {"symbol": alert.symbol, "action": alert.action, "price": price,
                      "status": status, "equity": round(self.engine.equity, 2)}
            if key is not None:
                self._seen[key] = result
                while len(self._seen) > self._dedupe_size:
                    self._seen.popitem(last=False)
            return result

    def check_stops(self) -> list[dict]:
        """Poll live prices and apply stops/take-profits to open positions."""
        out = []
        with self._lock:
            for symbol in list(self.engine.positions):
                try:
                    price = float(self.engine.venue.get_ticker(symbol))
                except Exception as e:
                    log.warning("stop_check_price_failed", symbol=symbol, error=str(e))
                    continue
                reason = self.engine.check_exits(symbol, price)
                if reason:
                    out.append({"symbol": symbol, "reason": reason, "price": price})
        return out

    def status(self) -> dict:
        eng = self.engine
        return {
            "venue": eng.venue.name,
            "mode": eng.settings.mode,
            "equity": round(eng.equity, 2),
            "kill_switch_active": eng.risk.state.kill_switch_active,
            "positions": {
                s: {"qty": p.qty, "entry": p.entry_price, "stop": p.stop_price,
                    "take_profit": None if math.isnan(p.take_profit) else p.take_profit,
                    "strategy": p.strategy_name}
                for s, p in eng.positions.items()
            },
        }
