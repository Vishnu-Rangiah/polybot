"""Run a promoted autoresearch strategy against Kalshi demo/prod plumbing.

Default behavior is a dry run: fetch live market data, build features, load the
promoted strategy, and print the proposed order. Pass `--place-order` to submit
one guarded order via `LiveExecutor` (demo by default).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kalshi_agent.autoresearch.evaluator import (
    current_best_validation,
    load_strategy_fn_from_file,
)
from kalshi_agent.autoresearch.registry import (
    DEFAULT_REGISTRY_PATH,
    load_strategy_candidate,
)
from kalshi_agent.autoresearch.types import (
    MarketState as AutoresearchMarketState,
    Order as AutoresearchOrder,
)
from kalshi_agent.datasource import RestDataSource
from kalshi_agent.executor import LiveExecutor
from kalshi_agent.risk import RiskGate, RiskLimits
from kalshi_agent.rule_parser import parse_ticker
from kalshi_agent.run import _load_env
from kalshi_agent.transport import DEMO_BASE, PROD_BASE, Transport, TransportError
from kalshi_agent.types import (
    MarketState as LiveMarketState,
    Order as LiveOrder,
    OrderAction,
    Side,
)
from kalshi_agent.weather import MeteoSource


def _creds(env: str) -> tuple[str, str]:
    if env == "demo":
        key_id = os.environ.get("KALSHI_DEMO_KEY_ID") or os.environ.get("KALSHI_KEY_ID")
        key_path = os.environ.get("KALSHI_DEMO_PRIVATE_KEY_PATH") or os.environ.get(
            "KALSHI_PRIVATE_KEY_PATH"
        )
    else:
        key_id = os.environ.get("KALSHI_KEY_ID")
        key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")

    if not key_id or not key_path:
        raise RuntimeError(f"Missing Kalshi credentials for {env}. Check .env.local.")
    return key_id, key_path


def _strategy_path(strategy_id: str | None, registry_path: Path) -> tuple[str, Path]:
    if strategy_id is None:
        best = current_best_validation(registry_path=registry_path)
        if best.strategy_id is None:
            raise RuntimeError(
                "No promoted strategy found. Run `uv run polybot registry list` "
                "or pass --strategy-id explicitly."
            )
        strategy_id = best.strategy_id

    candidate = load_strategy_candidate(strategy_id, registry_path=registry_path)
    return strategy_id, candidate.path / "strategy.py"


def _weather_features(ticker: str, *, as_of_date: str | None = None) -> dict[str, Any]:
    rule = parse_ticker(ticker)
    if rule is None:
        return {
            "resolution_ambiguity": "high",
            "feature_note": "Ticker was not recognized as a supported weather market.",
        }

    source = MeteoSource()
    if rule.kind == "rain":
        features = source.precip_features_for(rule.location_key, as_of_date=as_of_date)
        market_family = "weather_rain"
    elif rule.kind == "high_temp" and rule.threshold_f is not None:
        features = source.high_temp_features_for(
            rule.location_key, rule.threshold_f, as_of_date=as_of_date
        )
        market_family = "weather_high_temp"
    else:
        return {
            "market_family": "unsupported",
            "location": rule.location_key,
            "resolution_ambiguity": "high",
            "feature_note": "Parsed ticker, but no feature builder matched.",
        }

    fair = features.get("fair_prob_yes")
    return {
        **features,
        "market_family": market_family,
        "location": rule.location_key,
        "model_probability_yes": fair,
        "nws_probability_yes": fair,
        "probability_yes": fair,
        "resolution_ambiguity": "low" if fair is not None else "high",
        "rule_resolution_date": rule.resolution_date,
        "rule_threshold_f": rule.threshold_f,
    }


def _to_float_price(cents: int | None) -> float | None:
    return None if cents is None else round(cents / 100, 4)


def to_autoresearch_state(
    live_state: LiveMarketState,
    *,
    market: dict[str, Any],
    features: dict[str, Any],
) -> AutoresearchMarketState:
    observed = datetime.fromtimestamp(live_state.observed_at_ms / 1000, tz=UTC)
    return AutoresearchMarketState(
        ticker=live_state.ticker,
        timestamp_utc=observed.isoformat(),
        title=market.get("title"),
        series_ticker=market.get("series_ticker"),
        category=market.get("category"),
        yes_bid=_to_float_price(live_state.yes_bid),
        yes_ask=_to_float_price(live_state.yes_ask),
        no_bid=_to_float_price(live_state.no_bid),
        no_ask=_to_float_price(live_state.no_ask),
        volume=float(live_state.volume) if live_state.volume is not None else None,
        liquidity=float(live_state.top_liquidity),
        time_to_close_seconds=(
            None if live_state.time_to_close_ms is None else live_state.time_to_close_ms / 1000
        ),
        features=features,
    )


def to_live_order(ticker: str, order: AutoresearchOrder) -> LiveOrder:
    side = Side.YES if order.side == "yes" else Side.NO
    limit_cents = round(order.limit_price * 100)
    if limit_cents <= 0 or limit_cents >= 100:
        raise ValueError(f"Refusing invalid Kalshi limit price: {limit_cents}c")
    return LiveOrder(
        ticker=ticker,
        side=side,
        action=OrderAction.BUY,
        quantity=order.size,
        limit_cents=limit_cents,
    )


def _is_marketable(order: LiveOrder, state: LiveMarketState) -> tuple[bool, str]:
    ask = state.yes_ask if order.side is Side.YES else state.no_ask
    if ask is None:
        return False, f"No {order.side.value.upper()} ask is available."
    if order.limit_cents < ask:
        return False, f"Limit {order.limit_cents}c is below current ask {ask}c."
    return True, "marketable"


def _json_dump(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a promoted autoresearch strategy against Kalshi demo/prod."
    )
    parser.add_argument("--ticker", required=True, help="Kalshi market ticker to evaluate.")
    parser.add_argument("--env", choices=("demo", "prod"), default="demo")
    parser.add_argument("--strategy-id", default=None, help="Strategy candidate id; default=current promoted.")
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--as-of", default=None, help="Optional YYYY-MM-DD forecast date for features.")
    parser.add_argument("--place-order", action="store_true", help="Actually submit via LiveExecutor.")
    parser.add_argument(
        "--allow-resting",
        action="store_true",
        help="Do not auto-cancel resting quantity after place(). Default cancels.",
    )
    parser.add_argument(
        "--i-understand-real-money",
        action="store_true",
        help="Required with --env prod --place-order.",
    )
    parser.add_argument("--max-contracts-per-order", type=int, default=1)
    parser.add_argument("--max-position-per-market", type=int, default=10)
    parser.add_argument("--max-order-notional-cents", type=int, default=100)
    args = parser.parse_args()

    if args.place_order and args.env == "prod" and not args.i_understand_real_money:
        print("Refusing PROD order without --i-understand-real-money.", file=sys.stderr)
        return 1

    _load_env()
    key_id, key_path = _creds(args.env)
    base = DEMO_BASE if args.env == "demo" else PROD_BASE
    transport = Transport(key_id, key_path, base)

    strategy_id, source_path = _strategy_path(args.strategy_id, args.registry_path)
    strategy_fn = load_strategy_fn_from_file(source_path)

    ticker = args.ticker.upper()
    try:
        market = transport.get(f"/markets/{ticker}")["market"]
        if market.get("status") not in (None, "active", "open"):
            _json_dump(
                {
                    "action": "NO_TRADE",
                    "reason": f"Market is not active (status={market.get('status')!r}).",
                    "ticker": ticker,
                    "strategy_id": strategy_id,
                }
            )
            return 0

        features = _weather_features(ticker, as_of_date=args.as_of)
        live_state = RestDataSource(transport).get_state(ticker, features=features)
    except TransportError as exc:
        if args.env == "demo" and exc.status in (401, 403):
            print(
                "Demo auth failed. Kalshi demo and prod use separate keys; "
                "set KALSHI_DEMO_KEY_ID / KALSHI_DEMO_PRIVATE_KEY_PATH.",
                file=sys.stderr,
            )
        raise

    auto_state = to_autoresearch_state(live_state, market=market, features=features)
    proposed = strategy_fn(auto_state)

    report: dict[str, Any] = {
        "env": args.env,
        "base_url": base,
        "ticker": ticker,
        "strategy_id": strategy_id,
        "strategy_path": str(source_path),
        "market_status": market.get("status"),
        "market_title": market.get("title"),
        "features": features,
        "state": auto_state.to_dict(),
        "place_order": args.place_order,
    }

    if proposed is None:
        report.update({"action": "NO_TRADE", "reason": "Strategy returned None."})
        _json_dump(report)
        return 0

    live_order = to_live_order(ticker, proposed)
    marketable, marketable_reason = _is_marketable(live_order, live_state)
    report["proposed_autoresearch_order"] = proposed.to_dict()
    report["live_order"] = {
        "side": live_order.side.value,
        "action": live_order.action.value,
        "quantity": live_order.quantity,
        "limit_cents": live_order.limit_cents,
        "marketable": marketable,
        "marketable_reason": marketable_reason,
    }

    gate = RiskGate(
        RiskLimits(
            max_contracts_per_order=args.max_contracts_per_order,
            max_position_per_market=args.max_position_per_market,
            max_order_notional_cents=args.max_order_notional_cents,
        )
    )
    executor = LiveExecutor(transport, gate)

    if not marketable:
        report.update({"action": "NO_TRADE", "reason": marketable_reason})
        _json_dump(report)
        return 0

    if not args.place_order:
        report.update({"action": "DRY_RUN", "reason": "Pass --place-order to submit."})
        _json_dump(report)
        return 0

    ack = executor.place(live_order)
    report["order_ack"] = {
        "exchange_order_id": ack.exchange_order_id,
        "status": ack.status,
        "filled_qty": ack.filled_qty,
        "resting_qty": ack.resting_qty,
    }
    report["action"] = "ORDER_PLACED"

    if ack.exchange_order_id and ack.resting_qty > 0 and not args.allow_resting:
        cancel = executor.cancel(ack.exchange_order_id)
        report["resting_cancel"] = {
            "status": (cancel.get("order") or {}).get("status"),
            "reduced_by": cancel.get("reduced_by_fp") or cancel.get("reduced_by"),
        }

    _json_dump(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
