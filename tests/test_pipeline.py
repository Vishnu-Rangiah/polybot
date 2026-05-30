"""Tests for the kalshi_agent pipeline.

No network required: the WebSocket source's book-maintenance logic is tested by
feeding it synthetic snapshot/delta messages, exactly the shapes Kalshi sends.

Run standalone (no pytest needed):   uv run python tests/test_pipeline.py
Or with pytest if installed:         uv run pytest -q
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_agent.datasource import DataSource, WebSocketDataSource
from kalshi_agent.executor import Executor, PaperExecutor
from kalshi_agent.normalize import normalize
from kalshi_agent.risk import RiskGate, RiskLimits
from kalshi_agent.store import SnapshotStore
from kalshi_agent.strategy import decide
from kalshi_agent.types import MarketState, Order, OrderAction, Side


def _state(**kw) -> MarketState:
    base = dict(
        ticker="T", observed_at_ms=1,
        yes_bid=38, yes_ask=40, no_bid=60, no_ask=62,
        yes_bid_qty=100, no_bid_qty=100, features={"fair_prob_yes": 0.55},
    )
    base.update(kw)
    return MarketState(**base)


def test_normalize_derives_asks_independent_of_level_order():
    # Best bid must be the highest price regardless of array ordering. Feed the
    # YES side ascending and the NO side descending; both must resolve correctly.
    market = {"ticker": "T", "volume": 10}
    orderbook = {
        "yes": [[30, 5], [42, 7]],        # ascending; best yes bid = 42
        "no": [[55, 9], [50, 3]],         # descending; best no bid = 55
    }
    s = normalize(market, orderbook, observed_at_ms=123)
    assert s.yes_bid == 42 and s.yes_bid_qty == 7
    assert s.no_bid == 55 and s.no_bid_qty == 9
    assert s.yes_ask == 100 - 55 == 45   # yes_ask = 100 - best_no_bid
    assert s.no_ask == 100 - 42 == 58    # no_ask  = 100 - best_yes_bid
    assert s.top_liquidity == 16


def test_normalize_empty_side():
    s = normalize({"ticker": "T"}, {"yes": [], "no": [[60, 2]]}, observed_at_ms=1)
    assert s.yes_bid is None
    assert s.no_ask is None          # no yes bids -> no_ask underivable
    assert s.yes_ask == 40           # 100 - 60


def test_websocket_book_maintenance():
    # Build a source without starting a socket; drive _handle directly with the
    # exact message shapes Kalshi emits.
    ws = WebSocketDataSource(transport=None, tickers=["MKT"])
    assert isinstance(ws, DataSource)  # structural conformance to the interface

    ws._handle({
        "type": "orderbook_snapshot", "sid": 1, "seq": 1,
        "msg": {"market_ticker": "MKT",
                "yes": [[40, 100], [39, 50]],
                "no": [[58, 80]]},
    })
    s = ws.get_state("MKT")
    assert s.yes_bid == 40 and s.yes_bid_qty == 100
    assert s.no_bid == 58
    assert s.yes_ask == 42  # 100 - 58

    # Delta: 30 more contracts arrive at yes 41 -> becomes the new best yes bid.
    ws._handle({"type": "orderbook_delta", "seq": 2,
                "msg": {"market_ticker": "MKT", "price": 41, "delta": 30, "side": "yes"}})
    assert ws.get_state("MKT").yes_bid == 41

    # Delta: the 80 contracts at no 58 are fully removed -> level disappears.
    ws._handle({"type": "orderbook_delta", "seq": 3,
                "msg": {"market_ticker": "MKT", "price": 58, "delta": -80, "side": "no"}})
    s = ws.get_state("MKT")
    assert s.no_bid is None
    assert s.yes_ask is None  # no_bid gone -> yes_ask underivable


def test_websocket_real_dollar_string_format():
    # The exact shapes prod sends: snapshot uses *_dollars_fp, deltas use
    # price_dollars + delta_fp (dollar strings, not int cents).
    ws = WebSocketDataSource(transport=None, tickers=["MKT"])
    ws._handle({
        "type": "orderbook_snapshot", "sid": 1, "seq": 1,
        "msg": {"market_ticker": "MKT", "no_dollars_fp": [["0.9480", "216.00"]]},
    })
    s = ws.get_state("MKT")
    assert s.no_bid == 95            # 0.9480 -> 95c
    assert s.no_bid_qty == 216
    assert s.yes_ask == 5            # 100 - 95
    assert s.yes_bid is None         # one-sided book

    # Delta removes that level (delta_fp negative) -> book empties.
    ws._handle({"type": "orderbook_delta", "seq": 2, "msg": {
        "market_ticker": "MKT", "price_dollars": "0.9480",
        "delta_fp": "-216.00", "side": "no"}})
    assert ws.get_state("MKT").no_bid is None


def test_strategy_fires_on_edge_and_abstains_without():
    order = decide(_state())  # fair 0.55 (=55c) vs ask 40c, edge clears
    assert order is not None and order.side is Side.YES and order.limit_cents == 40

    assert decide(_state(features={})) is None              # no model prob
    assert decide(_state(features={"fair_prob_yes": 0.41})) is None  # 41-40-3 < 6
    assert decide(_state(yes_bid_qty=5, no_bid_qty=5)) is None        # too thin


def test_paper_executor_fills_and_updates_balance():
    gate = RiskGate(RiskLimits())
    ex = PaperExecutor(gate, starting_balance_cents=10_000, fee_cents=1)
    assert isinstance(ex, Executor)

    order = decide(_state())
    fill = ex.submit(order, state=_state())
    assert fill is not None and fill.price_cents == 40
    assert ex.balance_cents == 10_000 - 40 - 1
    pos = ex.position("T", Side.YES)
    assert pos.quantity == 1 and pos.avg_price_cents == 40


def test_paper_executor_not_marketable_returns_none():
    gate = RiskGate(RiskLimits())
    ex = PaperExecutor(gate, starting_balance_cents=10_000)
    # Limit below the ask -> not marketable -> no fill, balance unchanged.
    order = Order("T", Side.YES, OrderAction.BUY, quantity=1, limit_cents=35)
    assert ex.submit(order, state=_state()) is None
    assert ex.balance_cents == 10_000


def test_risk_gate_blocks_oversize_and_kill_switch():
    gate = RiskGate(RiskLimits(max_contracts_per_order=10))
    big = Order("T", Side.YES, OrderAction.BUY, quantity=50, limit_cents=40)
    d = gate.check(big, position=None, balance_cents=10_000)
    assert not d and "per-order cap" in d.reason

    killed = RiskGate(RiskLimits(kill_switch=True))
    d = killed.check(decide(_state()), position=None, balance_cents=10_000)
    assert not d and "kill switch" in d.reason


def test_snapshot_store_round_trips():
    with tempfile.TemporaryDirectory() as d:
        store = SnapshotStore(Path(d) / "snap.jsonl")
        original = _state(observed_at_ms=int(time.time() * 1000))
        store.append(original)
        store.append(_state(ticker="U"))
        replayed = list(store.replay())
        assert [s.ticker for s in replayed] == ["T", "U"]
        assert replayed[0].features == original.features  # dict survives JSONL


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
