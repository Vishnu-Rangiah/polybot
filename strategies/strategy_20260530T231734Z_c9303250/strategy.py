from __future__ import annotations

import math
from typing import Any

from strategy_types import MarketState, Order

MIN_LIQUIDITY = 25.0
MIN_NET_EDGE = 0.04
MAX_SPREAD = 0.12
MIN_ASK = 0.02
MAX_ASK = 0.98


def _clamp(v: float, a: float, b: float) -> float:
    return max(a, min(b, v))


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

    # Respect explicit ambiguity and basic liquidity gate
    ambiguity = state.features.get("resolution_ambiguity")
    if ambiguity == "high":
        return None

    if state.liquidity < MIN_LIQUIDITY:
        return None

    # Basic sanity on ask price
    if not (MIN_ASK < state.yes_ask < MAX_ASK):
        return None

    # Spread check when bid is present
    if state.yes_bid is not None:
        spread = state.yes_ask - state.yes_bid
        if spread < 0:
            return None
        if spread > MAX_SPREAD:
            return None
    else:
        spread = None

    # Family-specific tolerance: make thresholds adaptive
    market_family = state.features.get("market_family") or state.features.get("category")
    base_min_edge = MIN_NET_EDGE
    if market_family == "weather_high_temp":
        base_min_edge = max(0.02, MIN_NET_EDGE - 0.01)
    elif market_family == "weather_rain":
        base_min_edge = MIN_NET_EDGE + 0.01

    # Increase required edge as markets approach close (less time -> higher threshold)
    ttc = float(state.time_to_close_seconds or 0)
    # ramp from +0.00 at >48h to +0.02 at <=6h
    time_adj = 0.0
    if ttc <= 6 * 3600:
        time_adj = 0.02
    elif ttc <= 48 * 3600:
        # linear between 48h and 6h
        time_adj = 0.02 * (1.0 - (ttc - 6 * 3600) / (42 * 3600))

    # If ambiguity is medium and liquidity low, be more selective
    if ambiguity == "medium" and state.liquidity < 50:
        amb_adj = 0.02
    else:
        amb_adj = 0.0

    min_edge = _clamp(base_min_edge + time_adj + amb_adj, 0.01, 0.5)

    estimated_fee = estimate_fee_per_contract(state.yes_ask)
    estimated_slippage = 0.02 if state.liquidity < 100 else 0.01
    net_edge_ask = model_p - state.yes_ask - estimated_fee - estimated_slippage

    # Also check against mid-price when available to avoid paying an overpriced ask
    mid = None
    if state.yes_bid is not None:
        mid = (state.yes_bid + state.yes_ask) / 2.0

    if mid is not None:
        net_edge_mid = model_p - mid - estimated_fee
    else:
        net_edge_mid = net_edge_ask

    # Require the conservative (ask-based) net edge to beat threshold
    if net_edge_ask < min_edge:
        return None

    # Small extra sanity: require model to be meaningfully on the "yes" side
    if model_p - 0.5 < 0.03:
        return None

    # Determine size conservatively: default 1, allow 2 when liquidity & edge are high
    size = 1
    if state.liquidity > 500 and state.volume and state.volume > 100 and net_edge_ask > (min_edge + 0.08):
        size = 2

    return Order(side="yes", size=size, limit_price=state.yes_ask)
