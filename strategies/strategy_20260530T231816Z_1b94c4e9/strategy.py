from __future__ import annotations

import math
from typing import Any

from strategy_types import MarketState, Order

MIN_LIQUIDITY = 25.0
MIN_NET_EDGE = 0.04
MIN_NET_EDGE_MEDIUM_AMBIGUITY = 0.06
MIN_CONFIDENCE_DISTANCE = 0.08  # require model_p to be this far from 0.5
MAX_SIZE = 2


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def estimate_fee_per_contract(price: float) -> float:
    raw_cents = 0.07 * price * (1.0 - price) * 100
    return math.ceil(raw_cents) / 100


def decide(state: MarketState) -> Order | None:
    model_p = _as_float(
        state.features.get("model_probability_yes")
        or state.features.get("nws_probability_yes")
        or state.features.get("probability_yes")
    )
    yes_ask = _as_float(state.yes_ask)
    yes_bid = _as_float(state.yes_bid)

    if model_p is None or yes_ask is None:
        return None
    # Reject markets with very ambiguous resolution or low liquidity
    if state.features.get("resolution_ambiguity") == "high":
        return None

    # Family-aware liquidity gate: rain markets tend to be noisier, require more liquidity
    family = state.features.get("market_family")
    min_liq = MIN_LIQUIDITY
    if family == "weather_rain":
        min_liq = max(min_liq, 50.0)
    if state.liquidity < min_liq:
        return None

    # Require a minimum distance from 0.5 to avoid marginal predictions
    if abs(model_p - 0.5) < MIN_CONFIDENCE_DISTANCE:
        return None

    # Spread sanity check: avoid markets with very wide asks relative to bids
    if yes_bid is not None:
        spread = yes_ask - yes_bid
        # relative spread threshold (20% of price) or absolute 0.05
        if spread / max(1e-8, yes_ask) > 0.20 or spread > 0.05:
            return None

    # Dynamic slippage estimate: improves with liquidity
    if state.liquidity >= 500:
        estimated_slippage = 0.005
    elif state.liquidity >= 100:
        estimated_slippage = 0.01
    else:
        estimated_slippage = 0.02

    estimated_fee = estimate_fee_per_contract(yes_ask)

    # If ambiguity is medium, require a larger net edge
    min_net_edge = MIN_NET_EDGE
    if state.features.get("resolution_ambiguity") == "medium":
        min_net_edge = max(min_net_edge, MIN_NET_EDGE_MEDIUM_AMBIGUITY)

    net_edge = model_p - yes_ask - estimated_fee - estimated_slippage
    if net_edge < min_net_edge:
        return None

    # Conservative sizing: increase size only for large, confident edges and high liquidity
    size = 1
    if (
        net_edge >= 0.12
        and state.liquidity >= 200
        and (model_p >= 0.8 or model_p <= 0.2)
    ):
        size = min(MAX_SIZE, 2)

    return Order(side="yes", size=size, limit_price=yes_ask)
