#!/usr/bin/env python3
"""Polymarket CLOB connectivity smoke test (Step B).

Verifies the *trading* path end-to-end WITHOUT risking funds by default:
  1. authenticate (derive L2 API creds from your signing key)
  2. read USDC collateral balance/allowance
  3. fetch a live market + its order book from the public Gamma/CLOB APIs

Only with the explicit --place flag does it submit a tiny live order, and even
then it places a far-from-market limit (won't fill) and immediately cancels it.

Usage:
    cp .env.example .env          # fill in POLYMARKET_* trading vars first
    python scripts/polymarket_smoke_test.py
    python scripts/polymarket_smoke_test.py --approve         # one-time allowance
    python scripts/polymarket_smoke_test.py --place --token <token_id>   # live test
"""

from __future__ import annotations

import argparse
import sys

from quantbot.integrations.base import Order, OrderSide, OrderType
from quantbot.integrations.polymarket import PolymarketVenue, new_client_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--approve", action="store_true", help="set USDC allowance (gasless via relayer)")
    ap.add_argument("--place", action="store_true", help="submit + cancel a tiny non-marketable order")
    ap.add_argument("--token", default=None, help="CLOB token id to use for the order test")
    args = ap.parse_args()

    v = PolymarketVenue()
    print(f"CLOB={v.clob_url}  chain={v.chain_id}  sig_type={v.signature_type}  "
          f"funder={'set' if v.funder else 'none'}")

    # 1) Authenticate
    try:
        v.authenticate()
        print("✅ authenticated — L2 API creds derived")
    except Exception as e:
        print(f"❌ authenticate failed: {e}")
        print("   → check POLYMARKET_PRIVATE_KEY (and SIGNATURE_TYPE/FUNDER for proxy wallets)")
        return 1

    # 2) Balance / allowance
    try:
        bal = v.get_balances()[0]
        print(f"✅ USDC collateral: {bal.free:.4f}")
    except Exception as e:
        print(f"⚠️  balance read failed: {e}")

    if args.approve:
        try:
            v.update_allowance()
            print("✅ allowance updated (CLOB may now move your USDC)")
        except Exception as e:
            print(f"❌ allowance update failed: {e}")

    # 3) Public market data
    try:
        markets = v.list_markets(active=True, limit=1)
        print(f"✅ Gamma reachable — sample market: "
              f"{(markets[0].get('question') if markets else 'none')!r}")
    except Exception as e:
        print(f"⚠️  Gamma market fetch failed: {e}")

    # 4) Optional live order round-trip (non-marketable, then cancel)
    if args.place:
        if not args.token:
            print("❌ --place requires --token <token_id>")
            return 1
        try:
            order = Order(
                client_id=new_client_id(), symbol=args.token, side=OrderSide.BUY,
                type=OrderType.LIMIT, qty=5.0, limit_price=0.01,  # 1c — won't fill
            )
            res = v.submit_order(order)
            print(f"✅ order accepted id={res.venue_order_id} status={res.status.value}")
            if res.venue_order_id:
                v.cancel_order(res.venue_order_id)
                print("✅ order cancelled")
        except Exception as e:
            print(f"❌ order test failed: {e}")
            return 1

    print("\nDone. If auth + balance + market read all passed, the trading path is live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
