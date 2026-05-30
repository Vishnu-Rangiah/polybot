"""End-to-end wiring demo: DataSource -> strategy -> RiskGate -> Executor.

Run the paper loop with a baked-in fixture (no network, always works):
    uv run -m kalshi_agent.run

Run against live Kalshi data (still paper execution — never places real orders
unless you swap in LiveExecutor explicitly):
    uv run -m kalshi_agent.run --ticker SOME-TICKER

The point of this file is to show that the layers compose: each is constructed
once, wired by interface, and the strategy is oblivious to which DataSource or
Executor it's running against.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from kalshi_agent import strategy
from kalshi_agent.datasource import RestDataSource
from kalshi_agent.executor import PaperExecutor
from kalshi_agent.risk import RiskGate, RiskLimits
from kalshi_agent.rule_parser import parse_ticker
from kalshi_agent.store import SnapshotStore
from kalshi_agent.transport import DEMO_BASE, PROD_BASE, Transport
from kalshi_agent.types import MarketState
from kalshi_agent.weather import WEATHER_LOCATIONS, MeteoSource


def _fixture_state() -> MarketState:
    """A hand-built snapshot so the demo runs with zero dependencies.

    YES ask is 40c; the model thinks fair value is 0.55 -> edge clears threshold,
    so the strategy should fire a paper buy.
    """
    return MarketState(
        ticker="DEMO-RAIN-NYC",
        observed_at_ms=int(time.time() * 1000),
        yes_bid=38, yes_ask=40, no_bid=60, no_ask=62,
        yes_bid_qty=120, no_bid_qty=90,
        volume=5000, time_to_close_ms=6 * 3600 * 1000,
        features={"fair_prob_yes": 0.55},
    )


def _load_env(path: str = ".env.local") -> None:
    env_path = Path(__file__).resolve().parent.parent / path
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="live ticker; omit to use the fixture")
    parser.add_argument(
        "--weather", choices=sorted(WEATHER_LOCATIONS),
        help="attach an Open-Meteo rain probability as the fair_prob_yes feature",
    )
    parser.add_argument(
        "--as-of", dest="as_of",
        help="ISO date (YYYY-MM-DD) for a no-lookahead historical forecast; "
             "omit for the live forecast",
    )
    args = parser.parse_args()

    # Build the world. Each layer constructed once, wired by interface.
    gate = RiskGate(RiskLimits())
    executor = PaperExecutor(gate, starting_balance_cents=100_00, fee_cents=1)
    store = SnapshotStore("outputs/snapshots.jsonl")

    if args.ticker:
        _load_env()
        key_id = os.environ.get("KALSHI_KEY_ID")
        key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        if not key_id or not key_path:
            print("Missing KALSHI_KEY_ID / KALSHI_PRIVATE_KEY_PATH", file=sys.stderr)
            return 1
        base = DEMO_BASE if os.environ.get("KALSHI_ENV") == "demo" else PROD_BASE
        source = RestDataSource(Transport(key_id, key_path, base))
        # The model half: an Open-Meteo probability becomes the fair_prob_yes
        # feature.  Priority: explicit --weather flag > auto-parse from ticker.
        # Without either, features are left unset and the strategy abstains.
        features = None
        if args.weather:
            # Explicit override: treat the city as a rain market.
            features = MeteoSource().precip_features_for(args.weather, as_of_date=args.as_of)
            print(f"weather  {args.weather} fair_prob_yes={features['fair_prob_yes']} "
                  f"({features['weather_source']})")
        else:
            # Auto-parse the ticker; abstain (features=None) if unrecognised.
            rule = parse_ticker(args.ticker)
            if rule is None:
                print(f"ticker   {args.ticker!r} not recognised as a weather market "
                      f"— strategy will abstain")
            else:
                src = MeteoSource()
                if rule.kind == "rain":
                    print(f"parsed   rain | {rule.location_key} | {rule.resolution_date}")
                    features = src.precip_features_for(
                        rule.location_key, as_of_date=args.as_of
                    )
                elif rule.kind == "high_temp":
                    print(f"parsed   high_temp | {rule.location_key} | "
                          f"{rule.resolution_date} | threshold >= {rule.threshold_f}°F")
                    features = src.high_temp_features_for(
                        rule.location_key, rule.threshold_f, as_of_date=args.as_of
                    )
                if features is not None:
                    print(f"weather  fair_prob_yes={features['fair_prob_yes']} "
                          f"({features['weather_source']})")
        state = source.get_state(args.ticker, features=features)
    else:
        state = _fixture_state()

    # Record every observation -> this file IS the backtest dataset.
    store.append(state)

    print(f"market   {state.ticker}  yes_ask={state.yes_ask}c  liq={state.top_liquidity}")
    order = strategy.decide(state)
    if order is None:
        print("decision NO_TRADE (no edge / abstained)")
        return 0

    print(f"intent   BUY {order.quantity} {order.side} @ <= {order.limit_cents}c")
    fill = executor.submit(order, state=state)
    if fill is None:
        print("result   REJECTED by risk gate or not marketable")
    else:
        print(f"result   FILLED {fill.quantity} @ {fill.price_cents}c  "
              f"balance now {executor.balance_cents}c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
