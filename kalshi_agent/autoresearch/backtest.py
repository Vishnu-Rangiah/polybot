from __future__ import annotations

import argparse
import importlib
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from kalshi_agent.autoresearch.types import MarketState, Metrics, Order


StrategyFn = Callable[[MarketState], Order | None]


@dataclass(frozen=True)
class BacktestCase:
    split: str
    outcome_yes: bool
    state: MarketState


DEFAULT_CASES = [
    {
        "split": "train",
        "outcome_yes": True,
        "state": {
            "ticker": "KXRAINNYC-TRAIN-YES",
            "timestamp_utc": "2026-05-01T12:00:00+00:00",
            "title": "Will it rain in New York City?",
            "yes_bid": 0.41,
            "yes_ask": 0.48,
            "no_bid": 0.52,
            "no_ask": 0.59,
            "liquidity": 140.0,
            "time_to_close_seconds": 21600.0,
            "features": {
                "market_family": "weather_rain",
                "location": "NYC",
                "model_probability_yes": 0.62,
                "resolution_ambiguity": "medium",
            },
        },
    },
    {
        "split": "train",
        "outcome_yes": False,
        "state": {
            "ticker": "KXRAINNYC-TRAIN-NO",
            "timestamp_utc": "2026-05-02T12:00:00+00:00",
            "title": "Will it rain in New York City?",
            "yes_bid": 0.34,
            "yes_ask": 0.40,
            "no_bid": 0.60,
            "no_ask": 0.66,
            "liquidity": 95.0,
            "time_to_close_seconds": 21600.0,
            "features": {
                "market_family": "weather_rain",
                "location": "NYC",
                "model_probability_yes": 0.43,
                "resolution_ambiguity": "medium",
            },
        },
    },
    {
        "split": "train",
        "outcome_yes": True,
        "state": {
            "ticker": "KXHIGHNY-TRAIN-YES",
            "timestamp_utc": "2026-05-03T12:00:00+00:00",
            "title": "Will the high temperature in New York City be 80-81F?",
            "yes_bid": 0.18,
            "yes_ask": 0.24,
            "no_bid": 0.76,
            "no_ask": 0.82,
            "liquidity": 60.0,
            "time_to_close_seconds": 28800.0,
            "features": {
                "market_family": "weather_high_temp",
                "location": "NYC",
                "model_probability_yes": 0.36,
                "resolution_ambiguity": "medium",
            },
        },
    },
    {
        "split": "val",
        "outcome_yes": True,
        "state": {
            "ticker": "KXRAINNYC-VAL-YES",
            "timestamp_utc": "2026-05-04T12:00:00+00:00",
            "title": "Will it rain in New York City?",
            "yes_bid": 0.45,
            "yes_ask": 0.51,
            "no_bid": 0.49,
            "no_ask": 0.55,
            "liquidity": 125.0,
            "time_to_close_seconds": 18000.0,
            "features": {
                "market_family": "weather_rain",
                "location": "NYC",
                "model_probability_yes": 0.64,
                "resolution_ambiguity": "medium",
            },
        },
    },
    {
        "split": "val",
        "outcome_yes": False,
        "state": {
            "ticker": "KXRAINNYC-VAL-THIN",
            "timestamp_utc": "2026-05-05T12:00:00+00:00",
            "title": "Will it rain in New York City?",
            "yes_bid": 0.14,
            "yes_ask": 0.22,
            "no_bid": 0.78,
            "no_ask": 0.86,
            "liquidity": 18.0,
            "time_to_close_seconds": 18000.0,
            "features": {
                "market_family": "weather_rain",
                "location": "NYC",
                "model_probability_yes": 0.37,
                "resolution_ambiguity": "medium",
            },
        },
    },
    {
        "split": "test",
        "outcome_yes": False,
        "state": {
            "ticker": "KXHIGHNY-TEST-NO",
            "timestamp_utc": "2026-05-06T12:00:00+00:00",
            "title": "Will the high temperature in New York City be above 90F?",
            "yes_bid": 0.09,
            "yes_ask": 0.16,
            "no_bid": 0.84,
            "no_ask": 0.91,
            "liquidity": 80.0,
            "time_to_close_seconds": 28800.0,
            "features": {
                "market_family": "weather_high_temp",
                "location": "NYC",
                "model_probability_yes": 0.18,
                "resolution_ambiguity": "medium",
            },
        },
    },
]


def _load_strategy_fn(spec: str) -> StrategyFn:
    module_name, _, function_name = spec.partition(":")
    if not module_name or not function_name:
        raise ValueError("Strategy spec must look like 'module:function'.")

    module = importlib.import_module(module_name)
    strategy_fn = getattr(module, function_name)
    if not callable(strategy_fn):
        raise TypeError(f"{spec} is not callable.")
    return strategy_fn


def _case_from_dict(data: dict[str, Any]) -> BacktestCase:
    return BacktestCase(
        split=str(data["split"]),
        outcome_yes=bool(data["outcome_yes"]),
        state=MarketState.from_dict(data["state"]),
    )


def load_cases(path: Path | None = None) -> list[BacktestCase]:
    if path is None:
        return [_case_from_dict(case) for case in DEFAULT_CASES]

    cases = []
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            line = line.strip()
            if line:
                cases.append(_case_from_dict(json.loads(line)))
    return cases


def estimate_fee_per_contract(price: float) -> float:
    raw_cents = 0.07 * price * (1.0 - price) * 100
    return math.ceil(raw_cents) / 100


def estimate_slippage(liquidity: float) -> float:
    return 0.02 if liquidity < 100 else 0.01


def _fill_price(state: MarketState, order: Order) -> float | None:
    if order.side == "yes":
        if state.yes_ask is None or order.limit_price < state.yes_ask:
            return None
        return state.yes_ask

    if state.no_ask is None or order.limit_price < state.no_ask:
        return None
    return state.no_ask


def _trade_pnl(case: BacktestCase, order: Order) -> float | None:
    fill_price = _fill_price(case.state, order)
    if fill_price is None:
        return None

    fee = estimate_fee_per_contract(fill_price)
    slippage = estimate_slippage(case.state.liquidity)
    pays_out = case.outcome_yes if order.side == "yes" else not case.outcome_yes
    payout = 1.0 if pays_out else 0.0
    return (payout - fill_price - fee - slippage) * order.size


def _brier_score(cases: Iterable[BacktestCase]) -> float | None:
    errors = []
    for case in cases:
        raw_probability = case.state.features.get("model_probability_yes")
        if raw_probability is None:
            continue
        probability = float(raw_probability)
        outcome = 1.0 if case.outcome_yes else 0.0
        errors.append((probability - outcome) ** 2)
    if not errors:
        return None
    return mean(errors)


def _sharpe(pnls: list[float]) -> float:
    if len(pnls) < 2:
        return 0.0
    volatility = pstdev(pnls)
    if volatility == 0:
        return 0.0
    return mean(pnls) / volatility * math.sqrt(len(pnls))


def _max_drawdown(pnls: list[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for pnl in pnls:
        cumulative += pnl
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return max_dd


def backtest(strategy_fn: StrategyFn, *, split: str, cases: Iterable[BacktestCase] | None = None) -> Metrics:
    all_cases = load_cases() if cases is None else cases
    selected_cases = [case for case in all_cases if case.split == split]
    if not selected_cases:
        raise ValueError(f"No backtest cases found for split {split!r}.")

    pnls: list[float] = []
    for case in selected_cases:
        order = strategy_fn(case.state)
        if order is None:
            continue

        pnl = _trade_pnl(case, order)
        if pnl is not None:
            pnls.append(pnl)

    brier = _brier_score(selected_cases)
    return Metrics(
        pnl=round(sum(pnls), 4),
        sharpe=round(_sharpe(pnls), 4),
        brier=None if brier is None else round(brier, 4),
        n_trades=len(pnls),
        max_dd=round(_max_drawdown(pnls), 4),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen fixture backtester.")
    parser.add_argument(
        "--strategy",
        default="kalshi_agent.autoresearch.baseline:decide",
        help="Strategy function as module:function.",
    )
    parser.add_argument("--split", default="train", choices=["train", "val", "test"], help="Data split to score.")
    parser.add_argument("--cases-path", type=Path, default=None, help="Optional JSONL backtest case file.")
    args = parser.parse_args()

    strategy_fn = _load_strategy_fn(args.strategy)
    metrics = backtest(strategy_fn, split=args.split, cases=load_cases(args.cases_path))
    print(json.dumps(metrics.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
