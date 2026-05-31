from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_agent.demo_trade import to_autoresearch_state, to_live_order
from kalshi_agent.autoresearch.types import Order as AutoresearchOrder
from kalshi_agent.types import MarketState as LiveMarketState, OrderAction, Side


def test_to_autoresearch_state_converts_cents_to_float_contract():
    live = LiveMarketState(
        ticker="KXRAINNYC-26MAY31-T0",
        observed_at_ms=1_700_000_000_000,
        yes_bid=38,
        yes_ask=41,
        no_bid=58,
        no_ask=62,
        yes_bid_qty=12,
        no_bid_qty=8,
        volume=123,
        time_to_close_ms=60_000,
        features={"ignored": True},
    )
    market = {
        "title": "Will it rain in NYC?",
        "series_ticker": "KXRAINNYC",
        "category": "Weather",
    }
    features = {"model_probability_yes": 0.6, "resolution_ambiguity": "low"}

    converted = to_autoresearch_state(live, market=market, features=features)

    assert converted.ticker == live.ticker
    assert converted.yes_bid == 0.38
    assert converted.yes_ask == 0.41
    assert converted.no_bid == 0.58
    assert converted.no_ask == 0.62
    assert converted.liquidity == 20.0
    assert converted.time_to_close_seconds == 60
    assert converted.title == "Will it rain in NYC?"
    assert converted.features is features


def test_to_live_order_converts_autoresearch_order_to_buy_limit():
    order = to_live_order(
        "KXRAINNYC-26MAY31-T0",
        AutoresearchOrder(side="no", size=1, limit_price=0.37),
    )

    assert order.ticker == "KXRAINNYC-26MAY31-T0"
    assert order.side is Side.NO
    assert order.action is OrderAction.BUY
    assert order.quantity == 1
    assert order.limit_cents == 37
