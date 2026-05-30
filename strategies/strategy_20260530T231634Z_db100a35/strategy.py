from __future__ import annotations

import math
from typing import Any

from strategy_types import MarketState, Order

MIN_LIQUIDITY = 25.0
MIN_NET_EDGE = 0.04
MIN_TIME_TO_CLOSE = 3600.0  # seconds; avoid very-late trades
MAX_SIZE = 3


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
    if model_p is None:
        return None

    # basic safety gates
    if state.features.get("resolution_ambiguity") == "high":
        return None

    if state.liquidity < MIN_LIQUIDITY:
        return None

    if state.time_to_close_seconds is not None and state.time_to_close_seconds < MIN_TIME_TO_CLOSE:
        # avoid very-late bets where spreads/settlement noise dominate
        return None

    # Evaluate both sides (buy-yes or buy-no) after costs and slippage
    candidates: list[tuple[str, float, float]] = []  # (side, price, net_edge)
    for side in ("yes", "no"):
        price = _as_float(state.yes_ask if side == "yes" else state.no_ask)
        if price is None:
            continue
        model_prob = model_p if side == "yes" else 1.0 - model_p
        estimated_fee = estimate_fee_per_contract(price)
        estimated_slippage = 0.02 if state.liquidity < 100 else 0.01
        net_edge = model_prob - price - estimated_fee - estimated_slippage
        candidates.append((side, price, net_edge))

    if not candidates:
        return None

    # choose best positive net edge
    best = max(candidates, key=lambda t: t[2])
    best_side, best_price, best_net = best
    if best_net < MIN_NET_EDGE:
        return None

    # conservative, liquidity-aware sizing: scale up only for large, clear edges
    size = 1
    if state.liquidity >= 200 and best_net >= 0.08:
        size = 2
    if state.liquidity >= 500 and best_net >= 0.12:
        size = 3
    size = max(1, min(MAX_SIZE, int(size)))

    return Order(side=best_side, size=size, limit_price=best_price)
