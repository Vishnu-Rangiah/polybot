"""Strategy: a pure function `decide(state) -> Order | None`.

This is the only place "what to trade" lives, and it is deliberately tiny and
side-effect-free: it reads a `MarketState`, returns an intent, and touches
nothing else — no network, no positions, no risk math. That purity is what lets
the autoresearch loop iterate on this file alone while every other layer stays
frozen.
"""

from __future__ import annotations

from kalshi_agent.types import MarketState, Order, OrderAction, Side

# Fair value vs. ask must clear this many cents *after* an assumed cost buffer.
MIN_EDGE_CENTS = 6
COST_BUFFER_CENTS = 3
MIN_TOP_LIQUIDITY = 25


def decide(state: MarketState) -> Order | None:
    """Buy YES when our model probability beats the YES ask by enough edge.

    `features["fair_prob_yes"]` is the model's probability (0..1); compare it to
    the market's YES ask (cents). Edge = fair_cents - ask - cost_buffer.
    """
    fair_prob = state.features.get("fair_prob_yes")
    if fair_prob is None or state.yes_ask is None:
        return None

    if state.top_liquidity < MIN_TOP_LIQUIDITY:
        return None  # too thin to trust the quote

    fair_cents = round(fair_prob * 100)
    edge = fair_cents - state.yes_ask - COST_BUFFER_CENTS
    if edge < MIN_EDGE_CENTS:
        return None

    return Order(
        ticker=state.ticker,
        side=Side.YES,
        action=OrderAction.BUY,
        quantity=1,
        limit_cents=state.yes_ask,
    )
