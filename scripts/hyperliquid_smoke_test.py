#!/usr/bin/env python3
"""Hyperliquid connectivity smoke test (spot + perps trading path).

Verifies the trading path without risking funds by default:
  1. public market data (candles + mid) — no auth
  2. authenticate with the API-wallet key
  3. read account value / withdrawable + open positions
Only with --place does it submit a tiny far-from-market limit and cancel it.

Usage:
    cp .env.example .env     # set HYPERLIQUID_SECRET_KEY + HYPERLIQUID_ACCOUNT_ADDRESS
    python scripts/hyperliquid_smoke_test.py --coin BTC
    python scripts/hyperliquid_smoke_test.py --coin BTC --place
"""

from __future__ import annotations

import argparse
import sys

from quantbot.integrations.base import Order, OrderSide, OrderType
from quantbot.integrations.hyperliquid import HyperliquidVenue, new_client_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coin", default="BTC")
    ap.add_argument("--place", action="store_true", help="submit + cancel a tiny non-marketable order")
    args = ap.parse_args()

    v = HyperliquidVenue()
    print(f"network={'testnet' if v.testnet else 'mainnet'}")

    # 1) Public market data (no auth)
    try:
        candles = v.get_ohlcv(args.coin, "1h", limit=5)
        mid = v.get_ticker(args.coin)
        print(f"✅ market data — {args.coin} mid={mid} last_close={candles[-1].close if candles else 'n/a'}")
    except Exception as e:
        print(f"❌ market data failed: {e}")
        return 1

    # 2) Authenticate
    try:
        v.authenticate()
        print(f"✅ authenticated — account {v.address}")
    except Exception as e:
        print(f"❌ authenticate failed: {e}")
        print("   → set HYPERLIQUID_SECRET_KEY (API-wallet key) and HYPERLIQUID_ACCOUNT_ADDRESS (main wallet)")
        return 1

    # 3) Account state
    try:
        bal = v.get_balances()[0]
        positions = v.get_positions()
        print(f"✅ account value={bal.total:.2f} USDC  withdrawable={bal.free:.2f}  open_positions={len(positions)}")
        for p in positions:
            print(f"     {p.symbol}: qty={p.qty} entry={p.avg_price} uPnL={p.unrealized_pnl}")
    except Exception as e:
        print(f"⚠️  account read failed: {e}")

    # 4) Optional non-marketable order round-trip
    if args.place:
        try:
            mid = v.get_ticker(args.coin)
            px = round(mid * 0.5, 1)  # 50% below mid — won't fill
            order = Order(client_id=new_client_id(), symbol=args.coin, side=OrderSide.BUY,
                          type=OrderType.LIMIT, qty=0.001, limit_price=px)
            res = v.submit_order(order)
            print(f"✅ order status={res.status.value} oid={res.venue_order_id}")
            if res.venue_order_id:
                v.cancel_order(res.venue_order_id, symbol=args.coin)
                print("✅ order cancelled")
        except Exception as e:
            print(f"❌ order test failed: {e}")
            return 1

    print("\nDone. If market data + auth + account read passed, the trading path is live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
