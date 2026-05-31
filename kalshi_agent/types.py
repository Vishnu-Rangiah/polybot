"""The shared contract.

Every layer agrees on these types. Nothing here imports `requests`, knows a URL,
or references Kalshi's wire format — that isolation is the point. A strategy
written against `MarketState` runs unchanged against live, paper, or backtest
data sources.

Money convention: prices are **integer cents in [0, 100]**. A YES contract that
settles true pays 100c. We never use floats for money. Probabilities (model
estimates) are floats in [0.0, 1.0] and are clearly named `*_prob`.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field


class Side(enum.StrEnum):
    """Which contract you hold. Binary markets have exactly these two."""

    YES = "yes"
    NO = "no"


class OrderAction(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class MarketState:
    """A normalized point-in-time view of one market.

    Produced by every `DataSource` (REST poll, websocket tick, or historical
    replay) so downstream code can't tell which fed it. `observed_at_ms` is the
    wall-clock time we observed this snapshot — the anchor for no-lookahead
    backtesting, which keeps only data with `observed_at_ms < decision_time`.

    Prices are best top-of-book in cents. Kalshi only quotes YES/NO *bids*, so
    asks are derived once, here-adjacent (in normalize.py), and never recomputed:
        yes_ask = 100 - best_no_bid
        no_ask  = 100 - best_yes_bid
    A `None` price means that side of the book is empty.
    """

    ticker: str
    observed_at_ms: int

    yes_bid: int | None = None
    yes_ask: int | None = None
    no_bid: int | None = None
    no_ask: int | None = None

    # Top-of-book size on each side, in contracts. A liquidity guardrail.
    yes_bid_qty: int = 0
    no_bid_qty: int = 0

    volume: int | None = None
    time_to_close_ms: int | None = None

    # Strategy/research features (model probabilities, weather data, etc.).
    # Kept as a free dict so the contract doesn't churn when features change.
    features: dict = field(default_factory=dict)

    @property
    def yes_mid(self) -> float | None:
        """Midpoint of the YES book in cents, or None if either side is empty."""
        if self.yes_bid is None or self.yes_ask is None:
            return None
        return (self.yes_bid + self.yes_ask) / 2

    @property
    def top_liquidity(self) -> int:
        """Contracts resting at best bid across both sides — a thinness check."""
        return self.yes_bid_qty + self.no_bid_qty


@dataclass(frozen=True, slots=True)
class Order:
    """An *intent* to trade, emitted by a strategy.

    The strategy never talks to the exchange; it returns one of these and the
    executor decides how to realize it. `limit_cents` is the worst price you will
    accept (you buy at or below it). `client_order_id` is generated client-side
    so a network retry can't place the same order twice — idempotency is baked
    into the type, not left to the caller to remember.
    """

    ticker: str
    side: Side
    action: OrderAction
    quantity: int
    limit_cents: int
    client_order_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def notional_cents(self) -> int:
        """Max cash this order can consume (worst-case fill)."""
        return self.quantity * self.limit_cents


@dataclass(frozen=True, slots=True)
class Fill:
    """The result of an order actually trading, from any executor."""

    client_order_id: str
    ticker: str
    side: Side
    action: OrderAction
    quantity: int
    price_cents: int
    fee_cents: int = 0
    exchange_order_id: str | None = None  # None for paper fills

    def cash_delta_cents(self) -> int:
        """Signed cash effect: negative when buying, positive when selling."""
        gross = self.quantity * self.price_cents
        signed = -gross if self.action is OrderAction.BUY else gross
        return signed - self.fee_cents


@dataclass(frozen=True, slots=True)
class Position:
    """Net holding in one market. The executor reconciles this against the
    exchange so the bot's view and Kalshi's view never silently diverge."""

    ticker: str
    side: Side
    quantity: int
    avg_price_cents: int


@dataclass(frozen=True, slots=True)
class OrderAck:
    """The result of *placing* an order, whether or not it traded immediately.

    Distinct from `Fill` in two important ways:
      - A `Fill` only exists when contracts actually traded. An `OrderAck` is
        always returned — including for orders that REST on the book unfilled.
      - An `OrderAck` carries the `exchange_order_id` you need to cancel or
        poll a resting order. A `Fill` also carries it, but only after a trade;
        a resting order never produces a `Fill`, so without `OrderAck` the
        order_id would be silently lost and the order uncancellable.

    `resting_qty` = order.quantity - filled_qty. For a fully-filled order that
    is 0; for a resting order it equals the original quantity.
    `status` mirrors Kalshi's order status string: "resting", "executed",
    "canceled", or "rejected" (internal: risk-gate blocked, no POST made).
    """

    client_order_id: str
    exchange_order_id: str | None  # None only when risk-gate rejects (no POST)
    status: str                     # "resting"|"executed"|"canceled"|"rejected"
    filled_qty: int
    resting_qty: int


# --- historical / backtest vocabulary ------------------------------------------
# These extend the contract for evaluating strategies over resolved markets. They
# stay here, in the bottom layer, so both the scorer (metrics) and the engine
# (backtest) can depend on them without depending on each other.


@dataclass(frozen=True, slots=True)
class Candle:
    """One OHLC candlestick for a single market (Kalshi candlesticks endpoint).

    We keep only the close of each series: for a no-lookahead backtest the period
    close is the last value knowable within that period, so it is the honest
    decision-time quote. Prices are integer cents; `None` means that side had no
    quote during the period. Candles carry no resting-depth information.
    """

    ticker: str
    end_period_ts: int  # unix seconds; the period close == the no-lookahead anchor
    yes_bid_close: int | None = None
    yes_ask_close: int | None = None
    price_close: int | None = None
    volume: int = 0
    open_interest: int = 0


@dataclass(frozen=True, slots=True)
class Settlement:
    """How a market resolved, the ground truth a backtest scores against."""

    ticker: str
    result: str  # "yes" | "no" | "" (unsettled / unscored)
    settled_ts: int | None = None  # unix seconds

    @property
    def is_settled(self) -> bool:
        return self.result in ("yes", "no")

    def payout_cents(self, side: Side) -> int:
        """What one contract on `side` pays at settlement: 100c if it won, else 0."""
        won = (self.result == "yes" and side is Side.YES) or (
            self.result == "no" and side is Side.NO
        )
        return 100 if won else 0


@dataclass(frozen=True, slots=True)
class Prediction:
    """A decision-time model probability joined to the realized YES outcome."""

    ticker: str
    observed_at_ms: int
    fair_prob_yes: float
    outcome: int  # 1 if YES resolved true, else 0


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    """A fill held to settlement; the input to realized P&L."""

    ticker: str
    side: Side
    quantity: int
    entry_cents: int
    fee_cents: int
    settle_cents: int  # payout per contract at settlement, for the side held
    settled_ts: int | None = None

    def pnl_cents(self) -> int:
        """Realized P&L across all contracts: payout - cost - fees."""
        return self.quantity * (self.settle_cents - self.entry_cents) - self.fee_cents
