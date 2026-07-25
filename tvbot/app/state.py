"""SQLite persistence: signals, orders, positions, fills, and a small KV store.

Design notes
------------
* **Synchronous on purpose.** These are local-disk operations measured in
  microseconds, and the bot writes a handful of rows per hour on a 1H
  timeframe. Blocking the event loop for that long is cheaper and far easier to
  reason about than an async driver. If you move to a sub-minute timeframe,
  revisit this.
* **The idempotency guarantee lives in the database, not in application code.**
  ``claim_signal`` is an ``INSERT OR IGNORE`` on a PRIMARY KEY, so two
  concurrent deliveries of the same alert cannot both win, regardless of task
  interleaving.
* **"One open position per symbol" is enforced by a partial unique index**, so a
  logic bug in the engine surfaces as an IntegrityError rather than as two live
  positions on the same instrument.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import PositionStatus, SignalStatus

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS signals (
    signal_id     TEXT PRIMARY KEY,
    received_at   INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL,
    symbol        TEXT,
    side          TEXT,
    status        TEXT NOT NULL,
    reason        TEXT NOT NULL DEFAULT '',
    payload_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    client_order_id   TEXT UNIQUE,
    exchange_order_id TEXT,
    signal_id         TEXT,
    symbol            TEXT NOT NULL,
    purpose           TEXT NOT NULL,
    side              TEXT NOT NULL,
    order_type        TEXT NOT NULL,
    price             REAL,
    trigger_price     REAL,
    amount            REAL NOT NULL,
    filled            REAL NOT NULL DEFAULT 0,
    avg_price         REAL,
    status            TEXT NOT NULL,
    reduce_only       INTEGER NOT NULL DEFAULT 0,
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL,
    raw_json          TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_symbol_purpose ON orders(symbol, purpose, status);
CREATE INDEX IF NOT EXISTS idx_orders_signal ON orders(signal_id);

CREATE TABLE IF NOT EXISTS positions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL,
    signal_id     TEXT,
    side          TEXT NOT NULL,
    qty           REAL NOT NULL,
    entry_price   REAL NOT NULL,
    stop_price    REAL NOT NULL,
    target_price  REAL NOT NULL,
    stop_order_id TEXT,
    tp_order_id   TEXT,
    status        TEXT NOT NULL,
    opened_at     INTEGER NOT NULL,
    closed_at     INTEGER,
    realized_pnl  REAL,
    adopted       INTEGER NOT NULL DEFAULT 0
);
-- At most one OPEN position per symbol; closed rows accumulate as history.
CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_one_open_per_symbol
    ON positions(symbol) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_positions_closed_at ON positions(closed_at);

CREATE TABLE IF NOT EXISTS fills (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id  TEXT UNIQUE,
    order_id  TEXT,
    symbol    TEXT NOT NULL,
    side      TEXT NOT NULL,
    price     REAL NOT NULL,
    amount    REAL NOT NULL,
    fee       REAL NOT NULL DEFAULT 0,
    ts        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);
"""


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class PositionRow:
    id: int
    symbol: str
    signal_id: str | None
    side: str
    qty: float
    entry_price: float
    stop_price: float
    target_price: float
    stop_order_id: str | None
    tp_order_id: str | None
    status: str
    opened_at: int
    closed_at: int | None
    realized_pnl: float | None
    adopted: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> PositionRow:
        return cls(
            id=row["id"],
            symbol=row["symbol"],
            signal_id=row["signal_id"],
            side=row["side"],
            qty=row["qty"],
            entry_price=row["entry_price"],
            stop_price=row["stop_price"],
            target_price=row["target_price"],
            stop_order_id=row["stop_order_id"],
            tp_order_id=row["tp_order_id"],
            status=row["status"],
            opened_at=row["opened_at"],
            closed_at=row["closed_at"],
            realized_pnl=row["realized_pnl"],
            adopted=bool(row["adopted"]),
        )


class Store:
    """Thread-safe SQLite wrapper. One instance per process."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        if db_path != ":memory:":
            Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ signals
    def claim_signal(
        self,
        signal_id: str,
        payload_json: str,
        symbol: str | None,
        side: str | None,
    ) -> bool:
        """Atomically record a signal id. Returns False if already seen.

        This is the idempotency primitive. TradingView retries alerts, and a
        proxy in front of the bot may retry too; both must result in one order.
        """
        ts = now_ms()
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO signals
                    (signal_id, received_at, updated_at, symbol, side, status, reason, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, '', ?)
                """,
                (signal_id, ts, ts, symbol, side, SignalStatus.RECEIVED.value, payload_json),
            )
            return cur.rowcount == 1

    def set_signal_status(self, signal_id: str, status: SignalStatus, reason: str = "") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE signals SET status = ?, reason = ?, updated_at = ? WHERE signal_id = ?",
                (status.value, reason[:1000], now_ms(), signal_id),
            )

    def get_signal(self, signal_id: str) -> sqlite3.Row | None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,))
            return cur.fetchone()

    def count_signals(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) AS n FROM signals").fetchone()["n"])

    # ------------------------------------------------------------------- orders
    def record_order(
        self,
        *,
        client_order_id: str | None,
        exchange_order_id: str | None,
        signal_id: str | None,
        symbol: str,
        purpose: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        trigger_price: float | None = None,
        status: str = "open",
        filled: float = 0.0,
        avg_price: float | None = None,
        reduce_only: bool = False,
        raw: Any = None,
    ) -> int:
        ts = now_ms()
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO orders
                    (client_order_id, exchange_order_id, signal_id, symbol, purpose, side,
                     order_type, price, trigger_price, amount, filled, avg_price, status,
                     reduce_only, created_at, updated_at, raw_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(client_order_id) DO UPDATE SET
                    exchange_order_id = excluded.exchange_order_id,
                    status            = excluded.status,
                    filled            = excluded.filled,
                    avg_price         = excluded.avg_price,
                    updated_at        = excluded.updated_at
                """,
                (
                    client_order_id,
                    exchange_order_id,
                    signal_id,
                    symbol,
                    purpose,
                    side,
                    order_type,
                    price,
                    trigger_price,
                    amount,
                    filled,
                    avg_price,
                    status,
                    int(reduce_only),
                    ts,
                    ts,
                    json.dumps(raw, default=str) if raw is not None else None,
                ),
            )
            return int(cur.lastrowid or 0)

    def update_order(
        self,
        *,
        exchange_order_id: str,
        status: str | None = None,
        filled: float | None = None,
        avg_price: float | None = None,
        raw: Any = None,
    ) -> None:
        sets: list[str] = ["updated_at = ?"]
        args: list[Any] = [now_ms()]
        if status is not None:
            sets.append("status = ?")
            args.append(status)
        if filled is not None:
            sets.append("filled = ?")
            args.append(filled)
        if avg_price is not None:
            sets.append("avg_price = ?")
            args.append(avg_price)
        if raw is not None:
            sets.append("raw_json = ?")
            args.append(json.dumps(raw, default=str))
        args.append(exchange_order_id)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE orders SET {', '.join(sets)} WHERE exchange_order_id = ?", args
            )

    def get_order_by_client_id(self, client_order_id: str) -> sqlite3.Row | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)
            )
            return cur.fetchone()

    def orders_for_signal(self, signal_id: str) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM orders WHERE signal_id = ? ORDER BY id", (signal_id,)
            )
            return list(cur.fetchall())

    def count_orders(self, purpose: str | None = None) -> int:
        with self._lock:
            if purpose is None:
                sql, args = "SELECT COUNT(*) AS n FROM orders", ()
            else:
                sql, args = "SELECT COUNT(*) AS n FROM orders WHERE purpose = ?", (purpose,)
            return int(self._conn.execute(sql, args).fetchone()["n"])

    # ---------------------------------------------------------------- positions
    def open_position(
        self,
        *,
        symbol: str,
        signal_id: str | None,
        side: str,
        qty: float,
        entry_price: float,
        stop_price: float,
        target_price: float,
        stop_order_id: str | None = None,
        tp_order_id: str | None = None,
        adopted: bool = False,
    ) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO positions
                    (symbol, signal_id, side, qty, entry_price, stop_price, target_price,
                     stop_order_id, tp_order_id, status, opened_at, adopted)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    symbol,
                    signal_id,
                    side,
                    qty,
                    entry_price,
                    stop_price,
                    target_price,
                    stop_order_id,
                    tp_order_id,
                    PositionStatus.OPEN.value,
                    now_ms(),
                    int(adopted),
                ),
            )
            return int(cur.lastrowid or 0)

    def get_open_position(self, symbol: str) -> PositionRow | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM positions WHERE symbol = ? AND status = 'open'", (symbol,)
            )
            row = cur.fetchone()
            return PositionRow.from_row(row) if row else None

    def list_open_positions(self) -> list[PositionRow]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM positions WHERE status = 'open' ORDER BY id")
            return [PositionRow.from_row(r) for r in cur.fetchall()]

    def count_open_positions(self) -> int:
        with self._lock:
            return int(
                self._conn.execute(
                    "SELECT COUNT(*) AS n FROM positions WHERE status = 'open'"
                ).fetchone()["n"]
            )

    def update_position(
        self,
        position_id: int,
        *,
        qty: float | None = None,
        stop_order_id: str | None = None,
        tp_order_id: str | None = None,
    ) -> None:
        sets: list[str] = []
        args: list[Any] = []
        if qty is not None:
            sets.append("qty = ?")
            args.append(qty)
        if stop_order_id is not None:
            sets.append("stop_order_id = ?")
            args.append(stop_order_id)
        if tp_order_id is not None:
            sets.append("tp_order_id = ?")
            args.append(tp_order_id)
        if not sets:
            return
        args.append(position_id)
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE positions SET {', '.join(sets)} WHERE id = ?", args)

    def close_position(self, position_id: int, realized_pnl: float | None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE positions
                   SET status = ?, closed_at = ?, realized_pnl = ?
                 WHERE id = ?
                """,
                (PositionStatus.CLOSED.value, now_ms(), realized_pnl, position_id),
            )

    def recent_closed_positions(self, limit: int = 50) -> list[PositionRow]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM positions
                 WHERE status = 'closed' AND realized_pnl IS NOT NULL
                 ORDER BY closed_at DESC, id DESC
                 LIMIT ?
                """,
                (limit,),
            )
            return [PositionRow.from_row(r) for r in cur.fetchall()]

    def realized_pnl_since(self, since_ms: int) -> float:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(realized_pnl), 0.0) AS pnl
                  FROM positions
                 WHERE status = 'closed' AND closed_at >= ?
                """,
                (since_ms,),
            ).fetchone()
            return float(row["pnl"])

    # -------------------------------------------------------------------- fills
    def record_fill(
        self,
        *,
        trade_id: str | None,
        order_id: str | None,
        symbol: str,
        side: str,
        price: float,
        amount: float,
        fee: float = 0.0,
        ts: int | None = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO fills
                    (trade_id, order_id, symbol, side, price, amount, fee, ts)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (trade_id, order_id, symbol, side, price, amount, fee, ts or now_ms()),
            )

    def fills_for_order(self, order_id: str) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM fills WHERE order_id = ? ORDER BY ts", (order_id,)
            )
            return list(cur.fetchall())

    # ----------------------------------------------------------------------- kv
    def kv_get(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def kv_set(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO kv (key, value, updated_at) VALUES (?,?,?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                               updated_at = excluded.updated_at
                """,
                (key, value, now_ms()),
            )

    def kv_setdefault(self, key: str, value: str) -> str:
        """Set only if absent; return the effective value.

        Used for the daily equity anchor so the first observation of the UTC day
        wins and later restarts cannot silently re-baseline the loss limit.
        """
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO kv (key, value, updated_at) VALUES (?,?,?)",
                (key, value, now_ms()),
            )
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
            return row["value"]
