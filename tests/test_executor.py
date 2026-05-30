"""Offline unit tests for LiveExecutor.place(), .cancel(), and .get_order().

No network calls, no live orders — all HTTP is intercepted by _FakeTransport,
which records calls and returns canned response dicts matching the verified
Kalshi API shapes documented in executor.py.

Run standalone (no pytest needed):   uv run python tests/test_executor.py
Or with pytest if installed:         uv run pytest -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_agent.executor import LiveExecutor
from kalshi_agent.risk import RiskGate, RiskLimits
from kalshi_agent.types import Order, OrderAction, OrderAck, Side


# ---------------------------------------------------------------------------
# Fake transport
# ---------------------------------------------------------------------------

class _FakeTransport:
    """Records every call and returns canned responses. No network, no signing.

    The recording format is a list of dicts so tests can assert on method,
    path, body, and params independently without string hacks.
    """

    def __init__(
        self,
        *,
        balance_cents: int = 10_000,
        positions: list[dict] | None = None,
        post_response: dict | None = None,
        get_responses: dict[str, dict] | None = None,
        delete_responses: dict[str, dict] | None = None,
    ):
        # Canned data the fake serves.
        self._balance_cents = balance_cents
        self._positions = positions or []
        self._post_response = post_response or {}
        # Keyed by endpoint path so tests can set per-order responses.
        self._get_responses: dict[str, dict] = get_responses or {}
        self._delete_responses: dict[str, dict] = delete_responses or {}

        # Call log — inspected by assertions.
        self.calls: list[dict] = []

    # --- Transport interface -------------------------------------------------

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        self.calls.append({"method": "GET", "path": endpoint, "params": params})
        # Serve balance / positions endpoints used by LiveExecutor internals.
        if endpoint == "/portfolio/balance":
            return {"balance": self._balance_cents}
        if endpoint == "/portfolio/positions":
            return {"market_positions": self._positions}
        # Per-order GET (get_order).
        return self._get_responses.get(endpoint, {})

    def post(self, endpoint: str, json: dict) -> dict:
        self.calls.append({"method": "POST", "path": endpoint, "body": json})
        return self._post_response

    def delete(self, endpoint: str) -> dict:
        self.calls.append({"method": "DELETE", "path": endpoint})
        return self._delete_responses.get(endpoint, {})

    # --- Helpers for assertions ---------------------------------------------

    def recorded_calls(self, method: str) -> list[dict]:
        """All recorded calls for a given HTTP method."""
        return [c for c in self.calls if c["method"] == method]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_order(
    *,
    ticker: str = "TEST-TICKER",
    side: Side = Side.YES,
    action: OrderAction = OrderAction.BUY,
    quantity: int = 1,
    limit_cents: int = 1,
) -> Order:
    return Order(
        ticker=ticker, side=side, action=action,
        quantity=quantity, limit_cents=limit_cents,
    )


def _gate(*, max_contracts: int = 50, max_notional_cents: int = 50_00) -> RiskGate:
    return RiskGate(RiskLimits(
        max_contracts_per_order=max_contracts,
        max_order_notional_cents=max_notional_cents,
    ))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_place_resting_order_returns_ack_with_order_id():
    """place() on a resting order must return an OrderAck with exchange_order_id,
    status "resting", filled_qty 0, and resting_qty matching the original count."""
    fake = _FakeTransport(
        balance_cents=50_00,
        post_response={"order": {
            "order_id": "abc",
            "status": "resting",
            "fill_count_fp": "0",
        }},
    )
    executor = LiveExecutor(fake, _gate())
    order = _make_order(quantity=1, limit_cents=1)

    ack = executor.place(order)

    assert isinstance(ack, OrderAck)
    assert ack.exchange_order_id == "abc"
    assert ack.status == "resting"
    assert ack.filled_qty == 0
    assert ack.resting_qty == 1
    assert ack.client_order_id == order.client_order_id


def test_place_risk_rejected_returns_rejected_ack_without_post():
    """When the risk gate blocks an order, place() must return an OrderAck with
    status "rejected" and must NOT make any POST call to the exchange."""
    # Cap of 1 contract but we send 999 — gate will block it.
    fake = _FakeTransport(balance_cents=1_000_000)
    executor = LiveExecutor(fake, _gate(max_contracts=1))
    order = _make_order(quantity=999, limit_cents=1)

    ack = executor.place(order)

    assert ack.status == "rejected"
    assert ack.exchange_order_id is None
    assert ack.filled_qty == 0
    assert ack.resting_qty == 0
    # The fake must not have seen a POST.
    assert len(fake.recorded_calls("POST")) == 0


def test_place_partial_fill_returns_correct_counts():
    """place() with fill_count_fp "1" for a 3-contract order should have
    filled_qty=1 and resting_qty=2."""
    fake = _FakeTransport(
        balance_cents=50_00,
        post_response={"order": {
            "order_id": "xyz",
            "status": "resting",
            "fill_count_fp": "1",
        }},
    )
    executor = LiveExecutor(fake, _gate())
    order = _make_order(quantity=3, limit_cents=40)

    ack = executor.place(order)

    assert ack.filled_qty == 1
    assert ack.resting_qty == 2
    assert ack.exchange_order_id == "xyz"


def test_place_full_fill_returns_executed_status():
    """place() where fill_count_fp equals the full quantity should show
    filled_qty == quantity and resting_qty == 0."""
    fake = _FakeTransport(
        balance_cents=50_00,
        post_response={"order": {
            "order_id": "filled-order",
            "status": "executed",
            "fill_count_fp": "1",
        }},
    )
    executor = LiveExecutor(fake, _gate())
    order = _make_order(quantity=1, limit_cents=50)

    ack = executor.place(order)

    assert ack.status == "executed"
    assert ack.filled_qty == 1
    assert ack.resting_qty == 0


def test_cancel_issues_delete_to_correct_path():
    """cancel() must issue DELETE /portfolio/orders/{id} and return the body."""
    order_id = "abc"
    cancel_body = {"order": {"order_id": order_id, "status": "canceled"}}
    fake = _FakeTransport(
        balance_cents=50_00,
        delete_responses={f"/portfolio/orders/{order_id}": cancel_body},
    )
    executor = LiveExecutor(fake, _gate())

    result = executor.cancel(order_id)

    delete_calls = fake.recorded_calls("DELETE")
    assert len(delete_calls) == 1
    assert delete_calls[0]["path"] == f"/portfolio/orders/{order_id}"
    assert result == cancel_body


def test_get_order_issues_get_and_returns_inner_dict():
    """get_order() must issue GET /portfolio/orders/{id} and return the inner
    "order" dict, not the whole envelope."""
    order_id = "abc"
    order_dict = {"order_id": order_id, "status": "resting", "fill_count_fp": "0"}
    fake = _FakeTransport(
        balance_cents=50_00,
        get_responses={f"/portfolio/orders/{order_id}": {"order": order_dict}},
    )
    executor = LiveExecutor(fake, _gate())

    result = executor.get_order(order_id)

    get_calls = [c for c in fake.recorded_calls("GET")
                 if c["path"] == f"/portfolio/orders/{order_id}"]
    assert len(get_calls) == 1
    assert result == order_dict


def test_place_post_body_contains_required_fields():
    """The POST body for place() must include client_order_id, type "limit", and
    yes_price (for a YES order) equal to order.limit_cents. This guards against
    silent schema drift that would cause silent resting at the wrong price."""
    fake = _FakeTransport(
        balance_cents=50_00,
        post_response={"order": {
            "order_id": "body-check",
            "status": "resting",
            "fill_count_fp": "0",
        }},
    )
    executor = LiveExecutor(fake, _gate())
    order = _make_order(side=Side.YES, limit_cents=1)

    executor.place(order)

    post_calls = fake.recorded_calls("POST")
    assert len(post_calls) == 1
    body = post_calls[0]["body"]
    assert body["client_order_id"] == order.client_order_id
    assert body["type"] == "limit"
    assert body["yes_price"] == 1   # YES order -> yes_price field
    assert "no_price" not in body   # must not include the wrong side's field


def test_place_no_side_uses_no_price_field():
    """For a NO-side order, the POST body must use no_price, not yes_price."""
    fake = _FakeTransport(
        balance_cents=50_00,
        post_response={"order": {
            "order_id": "no-side",
            "status": "resting",
            "fill_count_fp": "0",
        }},
    )
    executor = LiveExecutor(fake, _gate())
    order = _make_order(side=Side.NO, limit_cents=5)

    executor.place(order)

    body = fake.recorded_calls("POST")[0]["body"]
    assert body["no_price"] == 5
    assert "yes_price" not in body


def test_submit_still_returns_none_for_resting_order():
    """submit()'s existing contract: resting order -> None (not an OrderAck).
    Ensures we didn't break the Executor Protocol interface."""
    fake = _FakeTransport(
        balance_cents=50_00,
        post_response={"order": {
            "order_id": "rest-submit",
            "status": "resting",
            "fill_count_fp": "0",
        }},
    )
    from kalshi_agent.types import MarketState
    executor = LiveExecutor(fake, _gate())
    order = _make_order(limit_cents=1)
    state = MarketState(ticker="TEST-TICKER", observed_at_ms=1,
                        yes_bid=40, yes_ask=60, no_bid=40, no_ask=60)

    result = executor.submit(order, state=state)

    assert result is None


def test_submit_returns_fill_when_filled():
    """submit() returns a Fill when fill_count_fp > 0, preserving existing callers."""
    from kalshi_agent.types import Fill, MarketState
    fake = _FakeTransport(
        balance_cents=50_00,
        post_response={"order": {
            "order_id": "filled-submit",
            "status": "executed",
            "fill_count_fp": "1",
            "taker_fees_dollars": "0.01",
        }},
    )
    executor = LiveExecutor(fake, _gate())
    order = _make_order(quantity=1, limit_cents=50)
    state = MarketState(ticker="TEST-TICKER", observed_at_ms=1,
                        yes_bid=40, yes_ask=50, no_bid=50, no_ask=60)

    fill = executor.submit(order, state=state)

    assert isinstance(fill, Fill)
    assert fill.quantity == 1
    assert fill.exchange_order_id == "filled-submit"


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

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
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
