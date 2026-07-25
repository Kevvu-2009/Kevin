"""Startup reconciliation and the background repair loop.

The invariant this module defends is simple and absolute:

    **Every open position has a live reduce-only stop on the exchange.**

Everything else here exists to restore that invariant after the ways it breaks
in practice: the process died between the entry fill and the stop placement, the
venue cancelled a conditional order, a partial fill left the stop sized wrong,
or someone opened a position by hand.

The loop is also where OCO is implemented. The stop is a conditional market
order and the take-profit is a resting reduce-only limit; neither venue-cancels
the other reliably, so when the position goes flat any surviving sibling is
cancelled here.

Webhooks are refused until the first reconciliation succeeds. Accepting a signal
before we know what we already hold is how a restarted bot ends up double-sized.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from .config import Settings
from .exchange import (
    ExchangeAPI,
    ExchangeCallFailed,
    FatalExchangeError,
    OrderState,
    PositionState,
    make_client_order_id,
)
from .notify import Notifier
from .sizing import round_to_step
from .state import PositionRow, Store

log = logging.getLogger(__name__)


@dataclass
class ReconcileReport:
    ok: bool = True
    symbols_checked: int = 0
    repairs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return self.ok and not self.repairs and not self.errors


class Reconciler:
    def __init__(
        self,
        cfg: Settings,
        exchange: ExchangeAPI,
        store: Store,
        notifier: Notifier,
    ) -> None:
        self.cfg = cfg
        self.ex = exchange
        self.store = store
        self.notifier = notifier
        self.ready = False
        self.last_run_ts: float = 0.0
        self.last_report: ReconcileReport | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    # ------------------------------------------------------------------ startup
    async def startup(self) -> ReconcileReport:
        """Reconcile once before the webhook is allowed to accept anything."""
        report = await self.reconcile_once()
        self.ready = report.ok
        if report.ok:
            log.info(
                "startup_reconcile_ok symbols=%d repairs=%d",
                report.symbols_checked,
                len(report.repairs),
            )
            if report.repairs:
                await self.notifier.warn(
                    "Startup reconciliation repaired state:\n- " + "\n- ".join(report.repairs)
                )
        else:
            log.error("startup_reconcile_failed errors=%s", report.errors)
            await self.notifier.critical(
                "Startup reconciliation FAILED - webhooks are being refused.\n- "
                + "\n- ".join(report.errors)
            )
        return report

    # --------------------------------------------------------------- main loop
    def start_background(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self.run_forever())

    async def stop_background(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown
                pass
            self._task = None

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.sleep(self.cfg.reconcile_interval_sec)
                if self._stopping.is_set():
                    return
                report = await self.reconcile_once()
                # A previously failed startup can recover here without a restart.
                if report.ok and not self.ready:
                    self.ready = True
                    await self.notifier.info("Reconciliation recovered; accepting webhooks again.")
                elif not report.ok:
                    self.ready = False
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001 - the loop must never die
                log.exception("reconcile_loop_error")
                await self.notifier.critical(
                    f"Reconcile loop error: {type(exc).__name__}: {exc}",
                    dedup_key="reconcile_loop_error",
                )

    # ------------------------------------------------------------ core routine
    async def reconcile_once(self) -> ReconcileReport:
        report = ReconcileReport()
        symbols = set(self.cfg.ccxt_symbols)
        # Also check anything we believe is open, even if it was removed from
        # SYMBOL_MAP since - dropping a symbol from config must not orphan a
        # live position.
        symbols.update(p.symbol for p in self.store.list_open_positions())

        for symbol in sorted(symbols):
            try:
                await self._reconcile_symbol(symbol, report)
                report.symbols_checked += 1
            except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the rest
                log.exception("reconcile_symbol_failed symbol=%s", symbol)
                report.ok = False
                report.errors.append(f"{symbol}: {type(exc).__name__}: {exc}")

        self.last_run_ts = time.time()
        self.last_report = report
        return report

    async def _reconcile_symbol(self, symbol: str, report: ReconcileReport) -> None:
        exchange_position = await self.ex.fetch_position(symbol)
        local = self.store.get_open_position(symbol)
        open_orders = await self.ex.fetch_open_orders(symbol)
        protective = [o for o in open_orders if o.reduce_only]

        if exchange_position is None:
            await self._handle_flat(symbol, local, protective, report)
            return

        if local is None:
            await self._adopt_unknown_position(symbol, exchange_position, protective, report)
            return

        await self._verify_protection(symbol, local, exchange_position, protective, report)

    # --------------------------------------------------------- flat on exchange
    async def _handle_flat(
        self,
        symbol: str,
        local: PositionRow | None,
        protective: list[OrderState],
        report: ReconcileReport,
    ) -> None:
        if local is not None:
            exit_price, how = await self._determine_exit(symbol, local)
            pnl = self._realized_pnl(local, exit_price) if exit_price is not None else None
            self.store.close_position(local.id, pnl)
            if exit_price is None:
                msg = f"EXIT {symbol} {local.side} qty={local.qty} (exit price unknown)"
            else:
                msg = (
                    f"EXIT {symbol} {local.side} qty={local.qty} "
                    f"entry {local.entry_price:.6g} -> exit {exit_price:.6g} ({how})"
                )
            if pnl is not None:
                msg += f" | PnL {pnl:+.2f} USDT"
            log.info("position_closed symbol=%s pnl=%s how=%s", symbol, pnl, how)
            report.repairs.append(f"{symbol}: closed local position ({how})")
            await self.notifier.info(msg)

        # OCO: the position is gone, so any surviving sibling must go too.
        for order in protective:
            ok = await self.ex.cancel_order(order.id, symbol)
            self.store.update_order(
                exchange_order_id=order.id, status="canceled" if ok else order.status
            )
            log.info("oco_sibling_cancelled symbol=%s order_id=%s ok=%s", symbol, order.id, ok)
            report.repairs.append(f"{symbol}: cancelled orphan reduce-only order {order.id}")

    # ------------------------------------------------- position we do not know
    async def _adopt_unknown_position(
        self,
        symbol: str,
        position: PositionState,
        protective: list[OrderState],
        report: ReconcileReport,
    ) -> None:
        """A live position with no local record - protect it, then shout.

        This happens after a crash between the entry fill and the stop
        placement, or if someone traded the account by hand. We cannot know the
        intended stop, so we synthesise the widest one the risk config permits
        and a matching 1:3 target, which is the only trade shape this system
        runs. That is a guess, hence the CRITICAL alert.
        """
        spec = await self.ex.market_spec(symbol)
        sign = 1 if position.side == "long" else -1
        stop_px = round_to_step(
            position.entry_price * (1 - sign * self.cfg.stop_dist_max_pct), spec.price_step
        )
        target_px = round_to_step(
            position.entry_price + sign * 3 * abs(position.entry_price - stop_px),
            spec.price_step,
        )
        synthetic_id = f"adopted-{symbol.replace('/', '').replace(':', '')}-{int(time.time())}"

        stop_id = self._first_stop_id(protective)
        tp_id = self._first_tp_id(protective)

        if stop_id is None:
            stop_id = await self._place_stop(
                symbol, position.side, position.qty, stop_px, synthetic_id
            )
        if tp_id is None:
            tp_id = await self._place_tp(
                symbol, position.side, position.qty, target_px, synthetic_id
            )

        self.store.open_position(
            symbol=symbol,
            signal_id=synthetic_id,
            side=position.side,
            qty=position.qty,
            entry_price=position.entry_price,
            stop_price=stop_px,
            target_price=target_px,
            stop_order_id=stop_id,
            tp_order_id=tp_id,
            adopted=True,
        )
        report.repairs.append(f"{symbol}: adopted untracked position qty={position.qty}")
        await self.notifier.critical(
            f"ADOPTED UNTRACKED POSITION {symbol} {position.side} qty={position.qty} "
            f"@ {position.entry_price:.6g}. Synthetic stop {stop_px:.6g} "
            f"({self.cfg.stop_dist_max_pct:.2%}) and target {target_px:.6g} were placed "
            "because the original levels are unknown. Review this manually.",
            dedup_key=f"adopted:{symbol}",
        )

    # ------------------------------------------------------- verify protection
    async def _verify_protection(
        self,
        symbol: str,
        local: PositionRow,
        position: PositionState,
        protective: list[OrderState],
        report: ReconcileReport,
    ) -> None:
        spec = await self.ex.market_spec(symbol)
        tolerance = max(spec.amount_step / 2, 1e-12)

        if abs(position.qty - local.qty) > tolerance:
            log.info(
                "position_qty_drift symbol=%s local=%s exchange=%s",
                symbol,
                local.qty,
                position.qty,
            )
            self.store.update_position(local.id, qty=position.qty)
            report.repairs.append(
                f"{symbol}: position qty corrected {local.qty} -> {position.qty}"
            )

        stops = [o for o in protective if o.type == "market"]
        tps = [o for o in protective if o.type == "limit"]

        # --- the stop: the invariant ----------------------------------------
        good_stop = next((o for o in stops if abs(o.amount - position.qty) <= tolerance), None)
        if good_stop is None:
            for stale in stops:
                await self.ex.cancel_order(stale.id, symbol)
                self.store.update_order(exchange_order_id=stale.id, status="canceled")
                report.repairs.append(
                    f"{symbol}: cancelled mis-sized stop {stale.id} "
                    f"({stale.amount} vs position {position.qty})"
                )
            new_id = await self._place_stop(
                symbol,
                position.side,
                position.qty,
                round_to_step(local.stop_price, spec.price_step),
                local.signal_id or f"repair-{local.id}",
            )
            if new_id is not None:
                self.store.update_position(local.id, stop_order_id=new_id)
                report.repairs.append(f"{symbol}: replaced missing stop -> {new_id}")
                await self.notifier.critical(
                    f"STOP WAS MISSING on {symbol} {position.side} qty={position.qty}. "
                    f"Replaced at {local.stop_price:.6g} (order {new_id}).",
                    dedup_key=f"stop_missing:{symbol}",
                )
            else:
                report.ok = False
                report.errors.append(f"{symbol}: FAILED to place a stop; position is unprotected")
                await self.notifier.critical(
                    f"UNPROTECTED POSITION {symbol} {position.side} qty={position.qty} - "
                    "stop placement failed. Manual intervention required NOW.",
                    dedup_key=f"unprotected:{symbol}",
                )
        elif good_stop.id != local.stop_order_id:
            self.store.update_position(local.id, stop_order_id=good_stop.id)

        # --- the take-profit: desirable, not critical ------------------------
        good_tp = next((o for o in tps if abs(o.amount - position.qty) <= tolerance), None)
        if good_tp is None:
            for stale in tps:
                await self.ex.cancel_order(stale.id, symbol)
                self.store.update_order(exchange_order_id=stale.id, status="canceled")
                report.repairs.append(f"{symbol}: cancelled mis-sized take-profit {stale.id}")
            new_id = await self._place_tp(
                symbol,
                position.side,
                position.qty,
                round_to_step(local.target_price, spec.price_step),
                local.signal_id or f"repair-{local.id}",
            )
            if new_id is not None:
                self.store.update_position(local.id, tp_order_id=new_id)
                report.repairs.append(f"{symbol}: replaced missing take-profit -> {new_id}")
        elif good_tp.id != local.tp_order_id:
            self.store.update_position(local.id, tp_order_id=good_tp.id)

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _first_stop_id(protective: list[OrderState]) -> str | None:
        return next((o.id for o in protective if o.type == "market"), None)

    @staticmethod
    def _first_tp_id(protective: list[OrderState]) -> str | None:
        return next((o.id for o in protective if o.type == "limit"), None)

    async def _place_stop(
        self, symbol: str, side: str, qty: float, price: float, signal_id: str
    ) -> str | None:
        try:
            order = await self.ex.create_stop_market(
                symbol, side, qty, price, make_client_order_id("s", signal_id, int(time.time()))
            )
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            log.error("reconcile_stop_placement_failed symbol=%s err=%s", symbol, exc)
            return None
        self.store.record_order(
            client_order_id=order.client_order_id,
            exchange_order_id=order.id,
            signal_id=signal_id,
            symbol=symbol,
            purpose="stop",
            side=order.side,
            order_type="market",
            amount=qty,
            trigger_price=price,
            status=order.status,
            reduce_only=True,
            raw=order.raw,
        )
        return order.id

    async def _place_tp(
        self, symbol: str, side: str, qty: float, price: float, signal_id: str
    ) -> str | None:
        try:
            order = await self.ex.create_tp_limit(
                symbol, side, qty, price, make_client_order_id("t", signal_id, int(time.time()))
            )
        except (FatalExchangeError, ExchangeCallFailed) as exc:
            log.error("reconcile_tp_placement_failed symbol=%s err=%s", symbol, exc)
            return None
        self.store.record_order(
            client_order_id=order.client_order_id,
            exchange_order_id=order.id,
            signal_id=signal_id,
            symbol=symbol,
            purpose="take_profit",
            side=order.side,
            order_type="limit",
            amount=qty,
            price=price,
            status=order.status,
            reduce_only=True,
            raw=order.raw,
        )
        return order.id

    async def _determine_exit(
        self, symbol: str, local: PositionRow
    ) -> tuple[float | None, str]:
        """Work out where a now-closed position actually exited."""
        for order_id, label, planned in (
            (local.stop_order_id, "stop", local.stop_price),
            (local.tp_order_id, "target", local.target_price),
        ):
            if not order_id:
                continue
            try:
                order = await self.ex.fetch_order(order_id, symbol)
            except (FatalExchangeError, ExchangeCallFailed):
                continue
            if order.filled > 0:
                return (order.average or planned), label
        try:
            mark = await self.ex.fetch_mark_price(symbol)
            if mark > 0:
                return mark, "mark price (exit order not identifiable)"
        except (FatalExchangeError, ExchangeCallFailed):
            pass
        return None, "unknown"

    @staticmethod
    def _realized_pnl(local: PositionRow, exit_price: float) -> float:
        """Gross PnL in quote currency. Fees and funding are not included."""
        sign = 1 if local.side == "long" else -1
        return (exit_price - local.entry_price) * local.qty * sign
