"""Executor: the interface that consumes `Order` and returns `Fill | None`.

Two implementations of one Protocol:
  - PaperExecutor: fills against an observed orderbook. No network, no risk to
    real money. The "paper-only" guardrail becomes structural, not a discipline.
  - LiveExecutor: POSTs to Kalshi, carrying the idempotency key so a retried
    submit can't double-fill.

Both run the order through the same RiskGate first. Swapping paper for live is
constructing a different object — no strategy or wiring changes.

`submit` returns a `Fill` if the order traded, or `None` if it was rejected
(risk) or rests unfilled (not marketable). A real system would also model
resting/partial orders; this keeps the lifecycle to its essential ends so the
skeleton stays legible.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kalshi_agent.risk import RiskGate
from kalshi_agent.transport import Transport
from kalshi_agent.types import Fill, MarketState, Order, OrderAck, OrderAction, Position, Side


@runtime_checkable
class Executor(Protocol):
    def submit(self, order, *, state: MarketState) -> Fill | None:
        """Attempt to execute `order`. `state` is the current market snapshot,
        used both for risk context and (in paper) the fill model."""
        ...


def _fp_to_int(value) -> int:
    """Parse Kalshi 'fixed point' fields, which arrive as strings ("5", "-3",
    "12.0") or plain numbers, into a rounded int. Used for *_fp count fields."""
    if value is None:
        return 0
    return round(float(value))


def _dollars_to_cents(value) -> int:
    """Parse a Kalshi '*_dollars' fixed-point string ("0.47") into integer cents."""
    if value is None:
        return 0
    return round(float(value) * 100)


def _marketable_price(order, state: MarketState) -> int | None:
    """The price an aggressive buy would pay right now, if it clears the limit.

    Buying YES lifts the YES ask; buying NO lifts the NO ask. Returns None if
    that side has no ask, or if the limit price doesn't reach it.
    """
    ask = state.yes_ask if order.side is Side.YES else state.no_ask
    if ask is None:
        return None
    if order.action is OrderAction.BUY and order.limit_cents >= ask:
        return ask
    return None


class PaperExecutor:
    """Simulated fills against the observed book. Tracks positions/balance in
    memory so the rest of the system behaves exactly as it would live."""

    def __init__(self, gate: RiskGate, *, starting_balance_cents: int, fee_cents: int = 0):
        self._gate = gate
        self.balance_cents = starting_balance_cents
        self.fee_cents = fee_cents
        self._positions: dict[tuple[str, Side], Position] = {}

    def position(self, ticker: str, side: Side) -> Position | None:
        return self._positions.get((ticker, side))

    def submit(self, order, *, state: MarketState) -> Fill | None:
        decision = self._gate.check(
            order, position=self.position(order.ticker, order.side),
            balance_cents=self.balance_cents,
        )
        if not decision:
            return None

        price = _marketable_price(order, state)
        if price is None:
            return None  # not marketable — would rest, which paper doesn't model

        fill = Fill(
            client_order_id=order.client_order_id,
            ticker=order.ticker,
            side=order.side,
            action=order.action,
            quantity=order.quantity,
            price_cents=price,
            fee_cents=self.fee_cents,
        )
        self._apply(fill)
        return fill

    def _apply(self, fill: Fill) -> None:
        self.balance_cents += fill.cash_delta_cents()
        key = (fill.ticker, fill.side)
        prev = self._positions.get(key)
        prev_qty = prev.quantity if prev else 0
        prev_cost = prev.avg_price_cents * prev_qty if prev else 0
        new_qty = prev_qty + fill.quantity
        new_avg = (prev_cost + fill.quantity * fill.price_cents) // new_qty
        self._positions[key] = Position(fill.ticker, fill.side, new_qty, new_avg)


class LiveExecutor:
    """Places real orders on Kalshi. Same interface as PaperExecutor.

    The idempotency key (`client_order_id`) rides along on the request body so a
    retry after a network blip is recognized by Kalshi as the same order rather
    than a second one. Position/balance come from `/portfolio`, never from local
    guesses — the exchange is the source of truth.
    """

    def __init__(self, transport: Transport, gate: RiskGate):
        self._t = transport
        self._gate = gate

    def _balance_cents(self) -> int:
        data = self._t.get("/portfolio/balance")
        # Newer API returns a "*_dollars" fixed-point string; older returns cents.
        if "balance" in data:
            return int(data["balance"])
        return _dollars_to_cents(data.get("balance_dollars"))

    def _position(self, ticker: str, side: Side) -> Position | None:
        data = self._t.get("/portfolio/positions", params={"ticker": ticker})
        for p in data.get("market_positions", []):
            # `position_fp` is signed: positive = net YES, negative = net NO.
            net = _fp_to_int(p.get("position_fp", p.get("position", 0)))
            if net == 0:
                continue
            held_side = Side.YES if net > 0 else Side.NO
            if held_side is not side:
                continue
            qty = abs(net)
            avg = _dollars_to_cents(p.get("market_exposure_dollars")) // qty if qty else 0
            return Position(ticker, side, qty, avg)
        return None

    def _order_body(self, order: Order) -> dict:
        """Build the JSON body for a limit order POST, shared by place() and submit().

        Centralising the body construction ensures both methods always send the
        same wire format. The price field name differs by side: Kalshi names it
        `yes_price` or `no_price` depending on which contract is being priced.
        """
        price_field = "yes_price" if order.side is Side.YES else "no_price"
        return {
            "ticker": order.ticker,
            "side": order.side.value,
            "action": order.action.value,
            "count": order.quantity,
            "type": "limit",
            price_field: order.limit_cents,
            "client_order_id": order.client_order_id,  # idempotency key
        }

    def place(self, order: Order) -> OrderAck:
        """POST a limit order and return an `OrderAck` regardless of fill status.

        Unlike `submit`, this never returns None — a resting order still carries
        the `exchange_order_id` you need to cancel it later. The risk gate is
        checked first; a blocked order gets status "rejected" and no POST is made
        (so it is still safe to call `place` without a separate gate call).

        `resting_qty` = order.quantity - filled_qty, so a fully-resting order
        has resting_qty == order.quantity and filled_qty == 0.
        """
        decision = self._gate.check(
            order, position=self._position(order.ticker, order.side),
            balance_cents=self._balance_cents(),
        )
        if not decision:
            return OrderAck(
                client_order_id=order.client_order_id,
                exchange_order_id=None,
                status="rejected",
                filled_qty=0,
                resting_qty=0,
            )

        resp = self._t.post("/portfolio/orders", json=self._order_body(order))
        o = resp.get("order", {})
        # Count fields are fixed-point strings on the current API; fall back to
        # legacy integer names so this survives either schema version.
        filled = _fp_to_int(o.get("fill_count_fp", o.get("filled_count", 0)))
        return OrderAck(
            client_order_id=order.client_order_id,
            exchange_order_id=o.get("order_id"),
            status=o.get("status", "unknown"),
            filled_qty=filled,
            resting_qty=order.quantity - filled,
        )

    def cancel(self, exchange_order_id: str) -> dict:
        """Cancel a resting order by its exchange-assigned order ID.

        Issues DELETE /portfolio/orders/{id}. Any 2xx response is treated as
        success; the body may contain {"order": {...}} or {"reduced_by": N}
        depending on API version — we return it raw so the caller can inspect.
        Raises `TransportError` on a non-2xx response.
        """
        return self._t.delete(f"/portfolio/orders/{exchange_order_id}")

    def get_order(self, exchange_order_id: str) -> dict:
        """Fetch the current state of one order from the exchange.

        Issues GET /portfolio/orders/{id}. Returns the inner "order" dict
        (fields: order_id, status, fill_count_fp, etc.) or {} if the response
        is unexpectedly shaped. Use this to confirm a resting order before or
        after cancellation.
        """
        resp = self._t.get(f"/portfolio/orders/{exchange_order_id}")
        return resp.get("order", {})

    def submit(self, order, *, state: MarketState) -> Fill | None:
        """Attempt to execute `order`. Returns a Fill if it traded, None otherwise.

        Runs the risk gate then POSTs the order body (shared with place() via
        _order_body). Returns None for risk-rejected orders or orders that rest
        unfilled — callers that need the exchange_order_id for a resting order
        should use place() instead.
        """
        decision = self._gate.check(
            order, position=self._position(order.ticker, order.side),
            balance_cents=self._balance_cents(),
        )
        if not decision:
            return None

        resp = self._t.post("/portfolio/orders", json=self._order_body(order))
        o = resp.get("order", {})
        # Count fields are fixed-point strings on the current API; fall back to
        # legacy integer names so this survives either schema version.
        filled = _fp_to_int(o.get("fill_count_fp", o.get("filled_count", 0)))
        if not filled:
            return None  # accepted but resting, or rejected — caller polls status
        return Fill(
            client_order_id=order.client_order_id,
            ticker=order.ticker,
            side=order.side,
            action=order.action,
            quantity=filled,
            # The taker fill price isn't a single field; record our limit as the
            # worst-case executed price (a documented simplification).
            price_cents=order.limit_cents,
            fee_cents=_dollars_to_cents(o.get("taker_fees_dollars")),
            exchange_order_id=o.get("order_id"),
        )
