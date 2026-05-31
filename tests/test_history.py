"""History tests: candle parsing, state reconstruction, and settlement reads.

A fake transport replays recorded-shape JSON so the fetchers are exercised
without touching Kalshi. The parsing helpers are pure and tested directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_agent.history import (
    ASSUMED_DEPTH,
    _parse_iso,
    _series_ticker,
    candle_to_state,
    fetch_candles,
    fetch_settlement,
    parse_candle,
)
from kalshi_agent.types import Side

# One candlestick in the exact shape the API returns (fixed-point dollar strings).
_RAW_CANDLE = {
    "end_period_ts": 1717200000,
    "yes_bid": {"close_dollars": "0.4000"},
    "yes_ask": {"close_dollars": "0.4200"},
    "price": {"close_dollars": "0.4100"},
    "volume_fp": "150.50",
    "open_interest_fp": "2000.00",
}


class _FakeTransport:
    """Returns canned responses keyed by endpoint — no network."""

    def __init__(self, responses: dict):
        self._responses = responses
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        self.calls.append((endpoint, params))
        return self._responses[endpoint]


def test_series_ticker_is_the_prefix():
    assert _series_ticker("KXRAINNYC-26MAY31-T0") == "KXRAINNYC"


def test_parse_iso_handles_z_suffix_and_none():
    assert _parse_iso("1970-01-01T00:00:00Z") == 0
    assert _parse_iso(None) is None
    assert _parse_iso("not-a-date") is None


def test_parse_candle_converts_dollars_to_cents():
    candle = parse_candle("KXRAINNYC-26MAY31-T0", _RAW_CANDLE)
    assert candle.yes_bid_close == 40
    assert candle.yes_ask_close == 42
    assert candle.price_close == 41
    assert candle.volume == 150  # 150.50 fixed-point -> rounded contracts
    assert candle.open_interest == 2000


def test_candle_to_state_mirrors_the_no_side_and_stamps_close_time():
    candle = parse_candle("T", _RAW_CANDLE)
    state = candle_to_state(candle, features={"fair_prob_yes": 0.55})
    assert state.yes_bid == 40 and state.yes_ask == 42
    # NO side is the mirror of YES.
    assert state.no_bid == 100 - 42
    assert state.no_ask == 100 - 40
    # observed_at_ms is the candle close in milliseconds (the no-lookahead anchor).
    assert state.observed_at_ms == 1717200000 * 1000
    assert state.yes_bid_qty == ASSUMED_DEPTH
    assert state.features["fair_prob_yes"] == 0.55


def test_fetch_candles_hits_the_series_path():
    t = _FakeTransport(
        {"/series/KXRAINNYC/markets/KXRAINNYC-26MAY31-T0/candlesticks": {
            "candlesticks": [_RAW_CANDLE]
        }}
    )
    candles = fetch_candles(
        t, "KXRAINNYC-26MAY31-T0", start_ts=0, end_ts=1717200000
    )
    assert len(candles) == 1 and candles[0].yes_ask_close == 42
    # the period_interval default is forwarded as a query param.
    assert t.calls[0][1]["period_interval"] == 60


def test_fetch_settlement_reads_result_and_timestamp():
    t = _FakeTransport(
        {"/markets/KXRAINNYC-26MAY31-T0": {
            "market": {"result": "yes", "settlement_ts": "2026-05-31T20:00:00Z"}
        }}
    )
    s = fetch_settlement(t, "KXRAINNYC-26MAY31-T0")
    assert s.result == "yes"
    assert s.is_settled
    assert s.payout_cents(Side.YES) == 100
    assert s.payout_cents(Side.NO) == 0


def test_fetch_settlement_unsettled_market():
    t = _FakeTransport({"/markets/T": {"market": {"result": ""}}})
    s = fetch_settlement(t, "T")
    assert not s.is_settled
    assert s.settled_ts is None


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
