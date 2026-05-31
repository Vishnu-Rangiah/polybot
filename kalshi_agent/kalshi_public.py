"""Unsigned Kalshi market reads for the weather research pipeline.

No API key required. Used by `kalshi_agent.research` memos and Modal fan-out.
For signed portfolio/order access, use `kalshi_agent.transport` or `kalshi_client`.
"""

from __future__ import annotations

from typing import Any

import requests

# Public reads need no auth. Use the canonical prod host verified by the live
# stack so the repo points at one Kalshi base.
KALSHI_PUBLIC_BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _get_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict:
    response = requests.get(url, params=params, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


def fetch_kalshi_market(ticker: str) -> dict:
    data = _get_json(f"{KALSHI_PUBLIC_BASE}/markets/{ticker}")
    return data["market"]


def fetch_kalshi_orderbook(ticker: str, depth: int = 5) -> dict:
    data = _get_json(f"{KALSHI_PUBLIC_BASE}/markets/{ticker}/orderbook", params={"depth": depth})
    return data.get("orderbook_fp") or data["orderbook"]


def _normalize_price(raw_price: str | int | float) -> float:
    price = float(raw_price)
    return price / 100 if price > 1 else price


def _best_bid(levels: list[list[str | int | float]]) -> tuple[float | None, float]:
    if not levels:
        return None, 0.0

    parsed = [(_normalize_price(price), float(quantity)) for price, quantity in levels]
    # Live responses are not guaranteed sorted, so choose by price, not position.
    price, quantity = max(parsed, key=lambda level: level[0])
    return round(price, 4), quantity


def normalize_orderbook(orderbook: dict) -> dict:
    yes_levels = (
        orderbook.get("yes_dollars")
        or orderbook.get("yes_dollars_fp")
        or orderbook.get("yes")
        or []
    )
    no_levels = (
        orderbook.get("no_dollars")
        or orderbook.get("no_dollars_fp")
        or orderbook.get("no")
        or []
    )
    yes_bid, yes_qty = _best_bid(yes_levels)
    no_bid, no_qty = _best_bid(no_levels)

    yes_ask = None if no_bid is None else round(1.0 - no_bid, 4)
    no_ask = None if yes_bid is None else round(1.0 - yes_bid, 4)

    return {
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "liquidity": yes_qty + no_qty,
    }
