"""The one place Kalshi's wire format is allowed to exist.

Kalshi quirks that live here and nowhere else:
  - Orderbooks quote YES *bids* and NO *bids*, never asks. We derive asks once:
        yes_ask = 100 - best_no_bid
        no_ask  = 100 - best_yes_bid
  - The live feeds disagree on key names for the same data, so we accept all:
        REST orderbook_fp:  yes_dollars      / no_dollars      (dollar strings)
        WS  snapshot:       yes_dollars_fp   / no_dollars_fp   (dollar strings)
        older/int form:     yes              / no              (integer cents)
    A level is `[price, qty]`; dollar strings ("0.9880") become integer cents.
  - `None` means an empty side of the book.

If Kalshi changes a field name, this is the only file that should need editing.
"""

from __future__ import annotations

from kalshi_agent.types import MarketState


def price_to_cents(value) -> int:
    """Parse a price into integer cents from either wire form.

    A dollar string/float ("0.9880", 0.98) becomes cents (round to nearest);
    an integer-cents value (98) passes through. We disambiguate by magnitude:
    Kalshi cents are 1..99, so a value < 1 must be dollars. Sub-cent fixed-point
    precision (0.988 -> 99) is rounded away, which the integer-cents contract
    accepts for now.
    """
    f = float(value)
    return round(f * 100) if f < 1 else round(f)


def parse_levels(container: dict, side: str) -> list[tuple[int, int]]:
    """Extract `[(price_cents, contracts), ...]` for one side ("yes"/"no"),
    trying every key name the REST and WS feeds use for the same data."""
    for dollars_key in (f"{side}_dollars", f"{side}_dollars_fp"):
        if container.get(dollars_key):
            return [(price_to_cents(p), round(float(q))) for p, q in container[dollars_key]]
    if container.get(side):  # integer-cents form
        return [(int(p), int(q)) for p, q in container[side]]
    return []


def best_bid(levels: list[tuple[int, int]]) -> tuple[int | None, int]:
    """Top-of-book (price_cents, contracts): the *highest* price level.

    Chosen by `max`, not by position, so it's correct whether the feed returns
    levels ascending or descending (the order isn't documented). (None, 0) if
    the side is empty.
    """
    if not levels:
        return None, 0
    price, qty = max(levels, key=lambda level: level[0])
    return price, qty


def normalize(
    market: dict,
    orderbook: dict,
    *,
    observed_at_ms: int,
    features: dict | None = None,
) -> MarketState:
    """Fold a raw `market` object + `orderbook` into one `MarketState`.

    `orderbook` is the inner book dict (the value of `orderbook_fp`/`orderbook`,
    or a websocket `msg`). `observed_at_ms` is stamped by the caller at fetch
    time — the no-lookahead anchor. Every source funnels through here, so one
    shape reaches everything downstream.
    """
    yes_bid, yes_qty = best_bid(parse_levels(orderbook, "yes"))
    no_bid, no_qty = best_bid(parse_levels(orderbook, "no"))

    return MarketState(
        ticker=market["ticker"],
        observed_at_ms=observed_at_ms,
        yes_bid=yes_bid,
        yes_ask=None if no_bid is None else 100 - no_bid,
        no_bid=no_bid,
        no_ask=None if yes_bid is None else 100 - yes_bid,
        yes_bid_qty=yes_qty,
        no_bid_qty=no_qty,
        volume=market.get("volume"),
        time_to_close_ms=market.get("time_to_close_ms"),
        features=features or {},
    )
