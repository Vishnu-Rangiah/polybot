from __future__ import annotations

import math
from typing import Any

from strategy_types import MarketState, Order


MIN_LIQUIDITY = 25.0
MIN_NET_EDGE = 0.06


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
    if model_p is None or state.yes_ask is None:
        return None

    if state.features.get("resolution_ambiguity") == "high":
        return None

    if state.liquidity < MIN_LIQUIDITY:
        return None

    estimated_fee = estimate_fee_per_contract(state.yes_ask)
    estimated_slippage = 0.02 if state.liquidity < 100 else 0.01
    net_edge = model_p - state.yes_ask - estimated_fee - estimated_slippage
    if net_edge < MIN_NET_EDGE:
        return None

    return Order(side="yes", size=1, limit_price=state.yes_ask)
