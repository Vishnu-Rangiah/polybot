"""Historical market data: candlesticks + settlement, and a replay stream.

This is what lets the agent evaluate a hypothesis *today* against markets that
have already resolved, instead of waiting days for live snapshots to settle.
Two reads from Kalshi:

  - candlesticks -> price history  (GET /series/{series}/markets/{ticker}/candlesticks)
  - the market   -> its settled `result`  (GET /markets/{ticker})

`candle_to_state` turns one candle into the same `MarketState` the live feed
produces, stamping `observed_at_ms` from the candle *close* so a strategy reading
it has no future information. `replay` streams those states in time order with
the as-of weather feature attached — the backtester's input.

A Kalshi candle carries `yes_bid` AND `yes_ask` directly, so we reconstruct
top-of-book without orderbook history (which Kalshi doesn't expose). The one
thing a candle lacks is resting depth, so historical liquidity is unknown — see
`candle_to_state` for the assumption that handles it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Iterator

from kalshi_agent.rule_parser import parse_ticker
from kalshi_agent.transport import Transport
from kalshi_agent.types import Candle, MarketState, Settlement
from kalshi_agent.weather import MeteoSource

# Candle periods Kalshi accepts, in minutes (1m / 1h / 1d).
HOUR_MINUTES = 60
DAY_MINUTES = 1440

# A candle has no resting-size info, so historical top-of-book depth is unknown.
# We stamp a sentinel size large enough to clear the strategy's liquidity gate:
# the backtest's documented assumption is "top-of-book was deep enough to fill
# the order". A depth-aware backtest is a later addition; faking a smaller number
# would be just as wrong and less honest about the gap.
ASSUMED_DEPTH = 10_000


def _series_ticker(ticker: str) -> str:
    """Series ticker = the prefix before the first '-'.

    `KXRAINNYC-26MAY31-T0` -> `KXRAINNYC`. Kalshi's candlestick path needs it,
    and the prefix encodes it without a second API round-trip.
    """
    return ticker.split("-")[0]


def _cents(dollars: object) -> int | None:
    """A Kalshi fixed-point dollar string ("0.5650") -> integer cents, or None."""
    if dollars is None:
        return None
    return round(float(dollars) * 100)


def _close(series: dict | None) -> int | None:
    """Pull the close of one OHLC sub-object (`yes_bid`, `yes_ask`, `price`)."""
    if not series:
        return None
    return _cents(series.get("close_dollars"))


def _parse_iso(value: object) -> int | None:
    """ISO-8601 ("2024-05-31T00:00:00Z") -> unix seconds, tolerant of None."""
    if not value or not isinstance(value, str):
        return None
    try:
        return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def parse_candle(ticker: str, raw: dict) -> Candle:
    """One raw candlestick object from the API -> a `Candle`. Pure (no network),
    so tests drive it directly with recorded fixtures."""
    return Candle(
        ticker=ticker,
        end_period_ts=int(raw["end_period_ts"]),
        yes_bid_close=_close(raw.get("yes_bid")),
        yes_ask_close=_close(raw.get("yes_ask")),
        price_close=_close(raw.get("price")),
        volume=round(float(raw.get("volume_fp") or 0)),
        open_interest=round(float(raw.get("open_interest_fp") or 0)),
    )


def fetch_candles(
    transport: Transport,
    ticker: str,
    *,
    start_ts: int,
    end_ts: int,
    period_interval: int = HOUR_MINUTES,
    series_ticker: str | None = None,
) -> list[Candle]:
    """Fetch candlesticks for one market over [start_ts, end_ts] (unix seconds).

    `period_interval` is the candle width in minutes (1, 60, or 1440). The series
    ticker is derived from the market ticker prefix unless given explicitly.
    """
    series = series_ticker or _series_ticker(ticker)
    resp = transport.get(
        f"/series/{series}/markets/{ticker}/candlesticks",
        params={
            "start_ts": start_ts,
            "end_ts": end_ts,
            "period_interval": period_interval,
        },
    )
    return [parse_candle(ticker, c) for c in resp.get("candlesticks", [])]


def fetch_settlement(transport: Transport, ticker: str) -> Settlement:
    """Fetch how a market resolved: its `result` and settlement timestamp.

    An unsettled (or non-binary) market comes back with `result == ""` and
    `is_settled == False`, which the backtester skips — you can't score an
    outcome that doesn't exist yet.
    """
    market = transport.get(f"/markets/{ticker}")["market"]
    return Settlement(
        ticker=ticker,
        result=market.get("result") or "",
        settled_ts=_parse_iso(market.get("settlement_ts")),
    )


def candle_to_state(candle: Candle, *, features: dict | None = None) -> MarketState:
    """Reconstruct the decision-time `MarketState` from one candle.

    Kalshi quotes YES bid/ask directly in the candle, so the NO side is the
    mirror (`no_bid = 100 - yes_ask`, `no_ask = 100 - yes_bid`) — the same
    relationship `normalize()` enforces for live data. `observed_at_ms` is the
    candle close: the no-lookahead anchor. Depth is the documented sentinel.
    """
    yes_bid = candle.yes_bid_close
    yes_ask = candle.yes_ask_close
    return MarketState(
        ticker=candle.ticker,
        observed_at_ms=candle.end_period_ts * 1000,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=None if yes_ask is None else 100 - yes_ask,
        no_ask=None if yes_bid is None else 100 - yes_bid,
        yes_bid_qty=ASSUMED_DEPTH,
        no_bid_qty=ASSUMED_DEPTH,
        volume=candle.volume,
        features=features or {},
    )


def replay(
    candles: Iterable[Candle], *, features: dict | None = None
) -> Iterator[MarketState]:
    """Yield `MarketState`s in chronological order, attaching `features` to each.

    Sorting by `end_period_ts` here is what makes the stream no-lookahead: the
    backtester asserts the timestamps only ever move forward, so a strategy can
    never see a later candle before an earlier one.
    """
    for candle in sorted(candles, key=lambda c: c.end_period_ts):
        yield candle_to_state(candle, features=features)


def weather_features_for(
    ticker: str, meteo: MeteoSource, *, as_of_date: str | None = None
) -> dict:
    """Derive the as-of weather feature dict for a weather-market ticker.

    Returns `{}` if the ticker isn't a recognized weather market (the strategy
    then abstains). `as_of_date` defaults to the market's own resolution date —
    the day the forecast is about. Using the archived forecast for that date is
    the MVP's documented simplification: it does not model intraday forecast
    revisions (that would need Open-Meteo's "previous runs" feed).
    """
    rule = parse_ticker(ticker)
    if rule is None:
        return {}
    as_of = as_of_date or rule.resolution_date
    if rule.kind == "rain":
        return meteo.precip_features_for(rule.location_key, as_of_date=as_of)
    if rule.kind == "high_temp" and rule.threshold_f is not None:
        return meteo.high_temp_features_for(
            rule.location_key, rule.threshold_f, as_of_date=as_of
        )
    return {}
