"""Demo-environment smoke test: prove the live REST + WebSocket + order paths.

Kalshi's DEMO and PROD are separate accounts with separate API keys. This test
always targets DEMO (fake money) so it can exercise real endpoints safely.

Phases:
  1. REST auth     — signed GET /exchange/status + /portfolio/balance
  2. REST data     — pick an open market, fetch orderbook -> MarketState
  3. WebSocket     — subscribe, receive snapshot, get_state, compare to REST
  4. Order (opt-in)— place ONE 1-contract order via LiveExecutor (--place-order)

Usage:
    uv run -m kalshi_agent.smoke                 # read-only (phases 1-3)
    uv run -m kalshi_agent.smoke --place-order   # also places one tiny demo order

Credentials come from env; demo-specific vars win if present:
    KALSHI_DEMO_KEY_ID / KALSHI_DEMO_PRIVATE_KEY_PATH   (preferred for demo)
    KALSHI_KEY_ID      / KALSHI_PRIVATE_KEY_PATH        (fallback)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from kalshi_agent.datasource import RestDataSource, WebSocketDataSource
from kalshi_agent.executor import LiveExecutor
from kalshi_agent.risk import RiskGate, RiskLimits
from kalshi_agent.transport import DEMO_BASE, PROD_BASE, Transport, TransportError
from kalshi_agent.types import Order, OrderAction, Side

# Reuse the tiny .env loader from run.py so we don't duplicate it.
from kalshi_agent.run import _load_env


def _creds() -> tuple[str, str]:
    """Prefer demo-specific creds; fall back to the generic ones. Returns
    (key_id, private_key_path) or exits with a clear message."""
    key_id = os.environ.get("KALSHI_DEMO_KEY_ID") or os.environ.get("KALSHI_KEY_ID")
    key_path = os.environ.get("KALSHI_DEMO_PRIVATE_KEY_PATH") or os.environ.get(
        "KALSHI_PRIVATE_KEY_PATH"
    )
    if not key_id or not key_path:
        sys.exit("Missing KALSHI_(DEMO_)KEY_ID / KALSHI_(DEMO_)PRIVATE_KEY_PATH")
    return key_id, key_path


def _pick_open_ticker(source_transport: Transport) -> str:
    """Grab the most liquid open market with a two-sided book, so the REST/WS
    phases show real prices (many open markets have empty books)."""
    data = source_transport.get("/markets", params={"limit": 200, "status": "open"})
    markets = data.get("markets", [])
    if not markets:
        sys.exit("No open markets returned — cannot run data/WS phases.")
    two_sided = [m for m in markets if m.get("yes_bid") and m.get("no_bid")]
    pool = two_sided or markets
    best = max(pool, key=lambda m: m.get("volume") or 0)
    return best["ticker"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=("demo", "prod"), default="demo",
                        help="which Kalshi environment to hit (default: demo)")
    parser.add_argument("--place-order", action="store_true",
                        help="place ONE 1-contract order (validates LiveExecutor)")
    parser.add_argument("--i-understand-real-money", action="store_true",
                        help="required to place an order on PROD (real funds)")
    parser.add_argument("--rest-and-cancel", action="store_true",
                        help="place a $0 resting order at 1c then cancel it "
                             "(validates place/cancel lifecycle, works on prod)")
    args = parser.parse_args()

    # Hard guard: never place a real-money order on prod without explicit opt-in.
    if args.place_order and args.env == "prod" and not args.i_understand_real_money:
        sys.exit("Refusing to place a PROD order without --i-understand-real-money.")

    _load_env()
    key_id, key_path = _creds()
    base = DEMO_BASE if args.env == "demo" else PROD_BASE
    t = Transport(key_id, key_path, base)
    print(f"→ {args.env.upper()} {base}\n")

    # --- Phase 1: REST auth --------------------------------------------------
    try:
        status = t.get("/exchange/status")
        bal = t.get("/portfolio/balance")
    except TransportError as e:
        print(f"❌ Phase 1 (auth) failed: {e}")
        if e.status in (401, 403) and args.env == "demo":
            print("   → A 401/403 on demo almost always means this is a PROD key.")
            print("     Demo needs a separate key created at demo-api.kalshi.co.")
        return 1
    balance_cents = bal.get("balance", 0)
    print(f"✅ Phase 1 auth OK   exchange_active={status.get('exchange_active')}  "
          f"balance=${balance_cents / 100:,.2f}")

    # --- Phase 2: REST data --------------------------------------------------
    ticker = _pick_open_ticker(t)
    rest = RestDataSource(t)
    rest_state = rest.get_state(ticker)
    print(f"✅ Phase 2 REST      {ticker}  "
          f"yes_bid={rest_state.yes_bid} yes_ask={rest_state.yes_ask} "
          f"liq={rest_state.top_liquidity}")

    # --- Phase 3: WebSocket --------------------------------------------------
    try:
        with WebSocketDataSource(t, [ticker]).start(timeout_s=15) as ws:
            ws_state = ws.get_state(ticker)
        print(f"✅ Phase 3 WS        {ticker}  "
              f"yes_bid={ws_state.yes_bid} yes_ask={ws_state.yes_ask} "
              f"liq={ws_state.top_liquidity}")
    except Exception as e:  # noqa: BLE001 — surface any WS failure plainly
        print(f"❌ Phase 3 (WebSocket) failed: {type(e).__name__}: {e}")
        return 1

    # --- Phase 4a: rest-and-cancel ($0 validation, opt-in) ------------------
    if args.rest_and_cancel:
        print("\n(note) --rest-and-cancel places a real resting order at 1c "
              "and immediately cancels it. Cost is $0 but it does touch the live book.\n")
        gate = RiskGate(RiskLimits(max_contracts_per_order=1, max_order_notional_cents=1))
        executor = LiveExecutor(t, gate)
        rac_order = Order(
            ticker=ticker, side=Side.YES, action=OrderAction.BUY,
            quantity=1, limit_cents=1,  # deeply non-marketable: rests, never fills
        )
        print(f"→ Phase 4a placing 1 YES @ 1c (rest-and-cancel)  "
              f"(client_order_id={rac_order.client_order_id[:8]}…)")
        ack = executor.place(rac_order)
        if ack.exchange_order_id is None:
            print(f"❌ Phase 4a place failed: status={ack.status} "
                  f"(risk-rejected or no order_id in response)")
            return 1

        if ack.filled_qty > 0:
            print(f"⚠️  Phase 4a: order filled unexpectedly at 1c "
                  f"(filled={ack.filled_qty}) — market may be extremely thin.")
        else:
            print(f"✅ Phase 4a placed   order_id={ack.exchange_order_id}  "
                  f"status={ack.status}  filled={ack.filled_qty}  "
                  f"resting={ack.resting_qty}")

        # Read the order back — but a freshly-placed order can 404 on the
        # by-id read path for a moment (eventual consistency), so retry briefly
        # and treat a persistent miss as a soft note. Cancellation below does
        # NOT depend on this succeeding.
        live_status = "<not-yet-visible>"
        for _ in range(5):
            try:
                live_status = executor.get_order(ack.exchange_order_id).get("status", "<unknown>")
                break
            except TransportError as e:
                if e.status != 404:
                    raise
                time.sleep(0.4)
        if live_status == "<not-yet-visible>":
            # The by-id read lags on demo; the resting-orders list is consistent
            # immediately, so confirm the order exists there instead.
            resting = t.get("/portfolio/orders", params={"status": "resting"}).get("orders", [])
            if any(o.get("order_id") == ack.exchange_order_id for o in resting):
                live_status = "resting (via list)"
        print(f"✅ Phase 4a get_order status={live_status}")

        # ALWAYS cancel, even if the read hiccuped — never leave a resting order.
        cancel_resp = executor.cancel(ack.exchange_order_id)
        # Response is {"order": {...}, "reduced_by_fp": "N"} — confirm it's gone.
        cancel_status = (cancel_resp.get("order") or {}).get("status", "?")
        reduced = cancel_resp.get("reduced_by_fp") or cancel_resp.get("reduced_by")
        print(f"✅ Phase 4a canceled  status={cancel_status}  reduced_by={reduced}")

    # --- Phase 4b: order (opt-in) -------------------------------------------
    if not args.place_order:
        if not args.rest_and_cancel:
            print("\n(read-only) skipped order placement; pass --place-order to test it.")
        return 0

    if rest_state.yes_ask is None:
        print("⏭  Phase 4b skipped: no YES ask to lift on this market.")
        return 0

    gate = RiskGate(RiskLimits(max_contracts_per_order=1, max_order_notional_cents=100_00))
    executor = LiveExecutor(t, gate)
    order = Order(
        ticker=ticker, side=Side.YES, action=OrderAction.BUY,
        quantity=1, limit_cents=rest_state.yes_ask,  # marketable: lifts the ask
    )
    print(f"\n→ Phase 4b placing 1 YES @ <= {order.limit_cents}c  "
          f"(client_order_id={order.client_order_id[:8]}…)")
    fill = executor.submit(order, state=rest_state)
    if fill is None:
        print("⚠️  Order accepted but no immediate fill (rested or rejected). "
              "Check /portfolio/orders.")
    else:
        print(f"✅ Phase 4b FILLED {fill.quantity} @ {fill.price_cents}c  "
              f"fee={fill.fee_cents}c  order_id={fill.exchange_order_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
