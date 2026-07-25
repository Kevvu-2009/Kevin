"""Entry execution pipeline.

One signal in, at most one protected position out. The ordering of steps is
deliberate and safety-critical:

    claim (atomic) -> risk gates -> server-side sizing -> slippage pre-check
    -> entry order -> wait for fill -> read position from the exchange
    -> place stop -> place take-profit -> persist

The claim happens first and synchronously in the webhook handler, so a
duplicate delivery cannot even enter this pipeline. The stop is placed before
the take-profit because an unprotected position is the only truly unacceptable
state; an position with a stop but no TP is merely suboptimal.

Protective orders are sized from the position the *exchange* reports, not from
our own arithmetic. If a partial fill, a rounding difference or a leftover
fragment means the real position is smaller than we think, a reduce-only exit
sized from local state would be rejected or would leave a remainder unprotected.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .config import Settings
from .exchange import (
    ExchangeAPI,
    ExchangeCallFailed,
    FatalExchangeError,
    OrderState,
    make_client_order_id,
)
from .models import OrderPurpose, SignalStatus, WebhookPayload
from .notify import Notifier
from .risk import RiskManager
from .sizing import (
    round_to_step,
    size_position,
    slippage_bounded_limit_price,
    within_slippage,
)
from .state import Store

log = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    status: str
    reason: str = ""
    signal_id: str = ""
    symbol: str = ""
    qty: float = 0.0
    entry_price: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def traded(self) -> bool:
        return self.status == "filled"


class Engine:
    def __init__(
        self,
        cfg: Settings,
        exchange: ExchangeAPI,
        store: Store,
        risk: RiskManager,
        notifier: Notifier,
    ) -> None:
        self.cfg = cfg
        self.ex = exchange
        self.store = store
        self.risk = risk
        self.notifier = notifier
        # Entries are rare on a 1H timeframe, so one global lock is simpler and
        # safer than per-symbol locks: it makes the "max positions total" check
        # and the position insert atomic with respect to each other.
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ idempotency
    def claim(self, payload: WebhookPayload) -> bool:
        """Atomically register the signal id. False means we have seen it before."""
        return self.store.claim_signal(
            payload.signal_id,
            payload.model_dump_json(exclude={"secret"}),
            payload.symbol,
            payload.side.value,
        )

    # --------------------------------------------------------------- pipeline
    async def execute_entry(self, payload: WebhookPayload) -> ExecutionResult:
        """Run the full entry pipeline for an already-claimed signal."""
        async with self._lock:
            try:
                return await self._execute_entry_locked(payload)
            except Exception as exc:  # noqa: BLE001 - background task boundary
                log.exception("entry_pipeline_unhandled signal_id=%s", payload.signal_id)
                self.store.set_signal_status(
                    payload.signal_id, SignalStatus.ERROR, f"{type(exc).__name__}: {exc}"
                )
                await self.notifier.critical(
                    f"Unhandled error executing {payload.symbol} {payload.side.value} "
                    f"({payload.signal_id}): {type(exc).__name__}: {exc}"
                )
                return ExecutionResult(
                    status="error", reason=str(exc), signal_id=payload.signal_id
                )

    async def _execute_entry_locked(self, payload: WebhookPayload) -> ExecutionResult:
        sid = payload.signal_id
        symbol = self.cfg.resolve_symbol(payload.symbol)
        if symbol is None:
            return await self._reject(
                payload, "unknown_symbol", f"{payload.symbol!r} is not in SYMBOL_MAP"
            )

        # --- equity + risk gates --------------------------------------------
        try:
            equity = await self.ex.fetch_equity()
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            return await self._reject(payload, "equity_unavailable", str(exc), notify=True)

        decision = self.risk.evaluate_entry(payload, symbol, equity)
        if not decision.allowed:
            return await self._reject(payload, decision.code, decision.reason, notify=True)

        # --- sizing (server-side, payload sizes never trusted) ---------------
        spec = await self.ex.market_spec(symbol)
        sizing = size_position(
            equity=equity,
            risk_pct=self.cfg.risk_pct,
            entry=payload.entry,
            stop=payload.stop,
            spec=spec,
            max_leverage=self.cfg.max_leverage,
        )
        if not sizing.ok:
            return await self._reject(payload, "sizing_rejected", sizing.reason, notify=True)
        if sizing.clamped_by_leverage:
            log.warning(
                "sizing_clamped_by_leverage signal_id=%s qty=%s leverage=%.3f",
                sid,
                sizing.qty,
                sizing.leverage,
            )

        # --- do not chase a market that has already moved --------------------
        mark = 0.0
        try:
            mark = await self.ex.fetch_mark_price(symbol)
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            log.warning("mark_price_unavailable symbol=%s err=%s", symbol, exc)
        if mark > 0 and not within_slippage(payload.entry, mark, self.cfg.max_slippage_pct):
            return await self._reject(
                payload,
                "slippage_exceeded",
                f"market at {mark} is more than {self.cfg.max_slippage_pct:.3%} "
                f"from signal entry {payload.entry}; not chasing",
                notify=True,
            )

        await self.ex.prepare_symbol(symbol, self.cfg.max_leverage)

        # --- entry order -----------------------------------------------------
        limit_price = slippage_bounded_limit_price(
            payload.entry, payload.is_long, self.cfg.max_slippage_pct, spec.price_step
        )
        entry_coid = make_client_order_id("e", sid)
        try:
            order = await self.ex.create_entry_limit(
                symbol, payload.side.entry_order_side, sizing.qty, limit_price, entry_coid
            )
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            return await self._reject(payload, "entry_order_failed", str(exc), notify=True)

        self.store.record_order(
            client_order_id=entry_coid,
            exchange_order_id=order.id,
            signal_id=sid,
            symbol=symbol,
            purpose=OrderPurpose.ENTRY.value,
            side=order.side,
            order_type="limit",
            amount=sizing.qty,
            price=limit_price,
            status=order.status,
            filled=order.filled,
            avg_price=order.average,
            raw=order.raw,
        )
        self.store.set_signal_status(sid, SignalStatus.SUBMITTED)
        log.info(
            "entry_submitted signal_id=%s symbol=%s side=%s qty=%s limit=%s order_id=%s",
            sid,
            symbol,
            payload.side.value,
            sizing.qty,
            limit_price,
            order.id,
        )

        # --- wait for the fill ----------------------------------------------
        final = await self._await_fill(order, symbol)
        self.store.update_order(
            exchange_order_id=final.id,
            status=final.status,
            filled=final.filled,
            avg_price=final.average,
            raw=final.raw,
        )

        if final.is_open:
            # Timed out with the order still working: cancel the remainder
            # rather than chase. Anything already filled is kept and protected.
            await self.ex.cancel_order(final.id, symbol)
            log.info(
                "entry_timeout_cancelled signal_id=%s filled=%s of %s",
                sid,
                final.filled,
                final.amount,
            )

        filled_qty = final.filled
        if filled_qty <= 0:
            self.store.set_signal_status(
                sid, SignalStatus.ABANDONED, "no fill within timeout; signal abandoned"
            )
            await self.notifier.info(
                f"No fill for {payload.symbol} {payload.side.value} within "
                f"{self.cfg.entry_fill_timeout_sec}s - signal abandoned ({sid})"
            )
            return ExecutionResult(
                status="abandoned", reason="no_fill", signal_id=sid, symbol=symbol
            )

        # --- protect the position -------------------------------------------
        # The exchange is the source of truth for how big the position actually is.
        position = await self.ex.fetch_position(symbol)
        protect_qty = position.qty if position is not None else filled_qty
        avg_entry = (position.entry_price if position is not None else None) or final.average or limit_price

        if position is None:
            log.warning(
                "position_not_visible_after_fill signal_id=%s filled=%s - "
                "protecting the filled quantity instead",
                sid,
                filled_qty,
            )

        stop_id, tp_id = await self._place_protection(
            symbol=symbol,
            signal_id=sid,
            position_side=payload.side.value,
            qty=protect_qty,
            stop_price=payload.stop,
            target_price=payload.target,
            spec_price_step=spec.price_step,
        )

        self.store.open_position(
            symbol=symbol,
            signal_id=sid,
            side=payload.side.value,
            qty=protect_qty,
            entry_price=avg_entry,
            stop_price=payload.stop,
            target_price=payload.target,
            stop_order_id=stop_id,
            tp_order_id=tp_id,
        )
        self.store.set_signal_status(sid, SignalStatus.FILLED)

        partial_note = ""
        if filled_qty < final.amount - 1e-12:
            partial_note = f" (partial: {filled_qty} of {final.amount})"

        await self.notifier.info(
            f"ENTRY FILLED {payload.symbol} {payload.side.value} qty={protect_qty} "
            f"@ {avg_entry:.6g}{partial_note} | stop {payload.stop:.6g} "
            f"target {payload.target:.6g} | risk {sizing.risk_cash:.2f} USDT "
            f"({self.cfg.risk_pct:.2%}) | lev {sizing.leverage:.2f}x"
        )
        if stop_id is None:
            await self.notifier.critical(
                f"POSITION WITHOUT STOP: {symbol} qty={protect_qty}. Stop placement "
                "failed; the reconcile loop will retry every "
                f"{self.cfg.reconcile_interval_sec}s. Intervene if it does not clear."
            )

        return ExecutionResult(
            status="filled",
            signal_id=sid,
            symbol=symbol,
            qty=protect_qty,
            entry_price=avg_entry,
            details={
                "stop_order_id": stop_id,
                "tp_order_id": tp_id,
                "leverage": sizing.leverage,
                "risk_cash": sizing.risk_cash,
                "partial": partial_note != "",
            },
        )

    # ---------------------------------------------------------------- helpers
    async def _await_fill(self, order: OrderState, symbol: str) -> OrderState:
        """Poll until the entry order is terminal or the timeout expires."""
        deadline = time.monotonic() + self.cfg.entry_fill_timeout_sec
        current = order
        while True:
            if not current.is_open:
                return current
            if time.monotonic() >= deadline:
                return current
            await asyncio.sleep(self.cfg.entry_poll_interval_sec)
            try:
                current = await self.ex.fetch_order(order.id, symbol)
            except (FatalExchangeError, ExchangeCallFailed) as exc:
                log.warning("fetch_order_failed id=%s err=%s", order.id, exc)
                # Keep waiting; a transient read failure is not a reason to
                # abandon an order that may well be filling.
                if time.monotonic() >= deadline:
                    return current

    async def _place_protection(
        self,
        *,
        symbol: str,
        signal_id: str,
        position_side: str,
        qty: float,
        stop_price: float,
        target_price: float,
        spec_price_step: float,
        nonce: int = 0,
    ) -> tuple[str | None, str | None]:
        """Place the reduce-only stop, then the reduce-only take-profit.

        Returns ``(stop_order_id, tp_order_id)``; either may be None if that
        order could not be placed. The caller must treat a missing stop as a
        critical condition.
        """
        stop_px = round_to_step(stop_price, spec_price_step)
        tp_px = round_to_step(target_price, spec_price_step)

        stop_id: str | None = None
        try:
            stop_order = await self.ex.create_stop_market(
                symbol,
                position_side,
                qty,
                stop_px,
                make_client_order_id("s", signal_id, nonce),
            )
            stop_id = stop_order.id
            self.store.record_order(
                client_order_id=stop_order.client_order_id,
                exchange_order_id=stop_order.id,
                signal_id=signal_id,
                symbol=symbol,
                purpose=OrderPurpose.STOP.value,
                side=stop_order.side,
                order_type="market",
                amount=qty,
                trigger_price=stop_px,
                status=stop_order.status,
                reduce_only=True,
                raw=stop_order.raw,
            )
            log.info("stop_placed symbol=%s qty=%s trigger=%s id=%s", symbol, qty, stop_px, stop_id)
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            log.error("stop_placement_failed symbol=%s qty=%s err=%s", symbol, qty, exc)

        tp_id: str | None = None
        try:
            tp_order = await self.ex.create_tp_limit(
                symbol,
                position_side,
                qty,
                tp_px,
                make_client_order_id("t", signal_id, nonce),
            )
            tp_id = tp_order.id
            self.store.record_order(
                client_order_id=tp_order.client_order_id,
                exchange_order_id=tp_order.id,
                signal_id=signal_id,
                symbol=symbol,
                purpose=OrderPurpose.TAKE_PROFIT.value,
                side=tp_order.side,
                order_type="limit",
                amount=qty,
                price=tp_px,
                status=tp_order.status,
                reduce_only=True,
                raw=tp_order.raw,
            )
            log.info("tp_placed symbol=%s qty=%s price=%s id=%s", symbol, qty, tp_px, tp_id)
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            log.error("tp_placement_failed symbol=%s qty=%s err=%s", symbol, qty, exc)

        return stop_id, tp_id

    async def _reject(
        self, payload: WebhookPayload, code: str, reason: str, notify: bool = False
    ) -> ExecutionResult:
        self.store.set_signal_status(payload.signal_id, SignalStatus.REJECTED, f"{code}: {reason}")
        log.info(
            "signal_rejected signal_id=%s code=%s reason=%s", payload.signal_id, code, reason
        )
        if notify:
            # Deduped per code so a persistent condition (halted, daily limit)
            # does not send one message per alert for the rest of the day.
            await self.notifier.warn(
                f"Signal rejected [{code}] {payload.symbol} {payload.side.value}: {reason}",
                dedup_key=f"reject:{code}:{payload.symbol}",
            )
        return ExecutionResult(
            status="rejected", reason=f"{code}: {reason}", signal_id=payload.signal_id
        )
