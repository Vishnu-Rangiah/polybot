"""Backtester: replay a resolved market's history through the live decision path
and score what the strategy would have done.

This file is meant to stay FROZEN. An agent iterating on a hypothesis edits
`strategy.py` (or passes its own `strategy_fn`); it never edits this. The loop is
deliberately the same one production runs:

    for state in replay(candles):      # no-lookahead: states in time order
        order = strategy_fn(state)     # the SAME pure decision function
        executor.submit(order, state)  # the SAME paper fill model
    settle open positions via the market's result

so a strategy that scores well here is judged by the machinery that will trade
it, not a parallel reimplementation that might flatter it.

Run it from the CLI against real resolved markets:

    uv run -m kalshi_agent.backtest --tickers KXRAINNYC-26MAY28-T0,KXRAINNYC-26MAY29-T0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from kalshi_agent import strategy
from kalshi_agent.history import (
    HOUR_MINUTES,
    fetch_candles,
    fetch_settlement,
    replay,
    weather_features_for,
)
from kalshi_agent.metrics import Metrics, kalshi_fee_cents, summarize
from kalshi_agent.executor import PaperExecutor
from kalshi_agent.risk import RiskGate, RiskLimits
from kalshi_agent.transport import DEMO_BASE, PROD_BASE, Transport
from kalshi_agent.types import (
    ClosedTrade,
    MarketState,
    OrderAction,
    Prediction,
    Settlement,
)
from kalshi_agent.weather import MeteoSource

StrategyFn = Callable[[MarketState], "object"]


@dataclass(frozen=True)
class BacktestConfig:
    starting_balance_cents: int = 100_00  # $100 of paper capital per market
    fee_multiplier: float = 0.07  # Kalshi's standard quadratic fee multiplier


@dataclass(frozen=True, slots=True)
class MarketHistory:
    """One resolved market's replay inputs: the chronological state stream, how
    it settled, and (implicitly, baked into the states) the as-of features."""

    ticker: str
    states: list[MarketState]
    settlement: Settlement


@dataclass(frozen=True, slots=True)
class BacktestResult:
    trades: list[ClosedTrade]
    predictions: list[Prediction]
    n_markets: int  # resolved markets actually scored

    def metrics(self) -> Metrics:
        return summarize(self.trades, self.predictions)


def _settle_fills(fills: Sequence, settlement: Settlement) -> list[ClosedTrade]:
    """Turn paper fills into closed trades by paying each out at settlement.

    MVP scope: the strategy only ever buys, so we settle long positions to their
    100c/0c payout. A strategy that sells to close would need richer accounting;
    we skip non-buy fills rather than mis-score them.
    """
    trades: list[ClosedTrade] = []
    for fill in fills:
        if fill.action is not OrderAction.BUY:
            continue
        trades.append(
            ClosedTrade(
                ticker=fill.ticker,
                side=fill.side,
                quantity=fill.quantity,
                entry_cents=fill.price_cents,
                fee_cents=fill.fee_cents,
                settle_cents=settlement.payout_cents(fill.side),
                settled_ts=settlement.settled_ts,
            )
        )
    return trades


def run_market(
    history: MarketHistory,
    strategy_fn: StrategyFn,
    *,
    gate: RiskGate,
    cfg: BacktestConfig,
) -> tuple[list[ClosedTrade], list[Prediction]]:
    """Replay one resolved market. Returns its closed trades and (if the model
    priced it) one prediction joined to the realized outcome.

    Three structural no-lookahead guards hold here:
      1. states arrive in increasing `observed_at_ms` (asserted below);
      2. their weather features are as-of the resolution date (set upstream);
      3. `settlement` is consulted only after the loop, never inside it.
    """
    if not history.settlement.is_settled:
        return [], []

    executor = PaperExecutor(
        gate,
        starting_balance_cents=cfg.starting_balance_cents,
        fee_model=lambda qty, price: kalshi_fee_cents(
            qty, price, multiplier=cfg.fee_multiplier
        ),
    )

    fills = []
    last_ms: int | None = None
    model_prob: float | None = None

    for state in history.states:
        if last_ms is not None and state.observed_at_ms < last_ms:
            raise ValueError(
                f"{history.ticker}: states out of order "
                f"({state.observed_at_ms} < {last_ms}) — lookahead risk"
            )
        last_ms = state.observed_at_ms

        fair = state.features.get("fair_prob_yes")
        if fair is not None:
            model_prob = fair  # remember the priced probability for calibration

        order = strategy_fn(state)
        if order is None:
            continue
        fill = executor.submit(order, state=state)
        if fill is not None:
            fills.append(fill)

    trades = _settle_fills(fills, history.settlement)

    predictions: list[Prediction] = []
    if model_prob is not None:
        predictions.append(
            Prediction(
                ticker=history.ticker,
                observed_at_ms=last_ms or 0,
                fair_prob_yes=model_prob,
                outcome=1 if history.settlement.result == "yes" else 0,
            )
        )
    return trades, predictions


def backtest(
    histories: Iterable[MarketHistory],
    strategy_fn: StrategyFn | None = None,
    *,
    gate: RiskGate | None = None,
    cfg: BacktestConfig | None = None,
) -> BacktestResult:
    """Score a strategy over many resolved markets. Unsettled markets are skipped.

    Defaults to the project strategy and standard risk limits, so the common case
    is `backtest(histories)`. Pass `strategy_fn` to evaluate a hypothesis variant.
    """
    strategy_fn = strategy_fn or strategy.decide
    gate = gate or RiskGate(RiskLimits())
    cfg = cfg or BacktestConfig()

    all_trades: list[ClosedTrade] = []
    all_preds: list[Prediction] = []
    n_markets = 0

    for history in histories:
        if not history.settlement.is_settled:
            continue
        n_markets += 1
        trades, preds = run_market(history, strategy_fn, gate=gate, cfg=cfg)
        all_trades.extend(trades)
        all_preds.extend(preds)

    return BacktestResult(
        trades=all_trades, predictions=all_preds, n_markets=n_markets
    )


# --- network loader + CLI ------------------------------------------------------


def load_histories(
    transport: Transport,
    tickers: Sequence[str],
    *,
    lookback_days: int = 30,
    period_interval: int = HOUR_MINUTES,
    meteo: MeteoSource | None = None,
) -> list[MarketHistory]:
    """Fetch candles + settlement + as-of weather features for each ticker.

    Network-bound: the backtester's input. Tests build `MarketHistory` directly
    from fixtures instead. The candle window runs from `lookback_days` before
    settlement up to settlement; an unsettled market still loads (no candle
    window) and is later skipped by `backtest`.
    """
    meteo = meteo or MeteoSource()
    histories: list[MarketHistory] = []

    for ticker in tickers:
        settlement = fetch_settlement(transport, ticker)
        states: list[MarketState] = []
        if settlement.settled_ts is not None:
            end_ts = settlement.settled_ts
            start_ts = end_ts - lookback_days * 86_400
            candles = fetch_candles(
                transport,
                ticker,
                start_ts=start_ts,
                end_ts=end_ts,
                period_interval=period_interval,
            )
            features = weather_features_for(ticker, meteo)
            states = list(replay(candles, features=features))
        histories.append(MarketHistory(ticker, states, settlement))

    return histories


def _load_env(path: str = ".env.local") -> None:
    """Minimal .env loader, mirroring run.py — three vars, no dependency."""
    env_path = Path(__file__).resolve().parent.parent / path
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backtest the strategy over resolved Kalshi markets."
    )
    parser.add_argument(
        "--tickers", required=True, help="comma-separated resolved market tickers"
    )
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument(
        "--interval",
        type=int,
        default=HOUR_MINUTES,
        help="candle period in minutes (1, 60, or 1440)",
    )
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        print("No tickers given.", file=sys.stderr)
        return 1

    _load_env()
    key_id = os.environ.get("KALSHI_KEY_ID")
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
    if not key_id or not key_path:
        print("Missing KALSHI_KEY_ID / KALSHI_PRIVATE_KEY_PATH", file=sys.stderr)
        return 1
    base = DEMO_BASE if os.environ.get("KALSHI_ENV") == "demo" else PROD_BASE
    transport = Transport(key_id, key_path, base)

    started = time.time()
    histories = load_histories(
        transport, tickers, lookback_days=args.lookback_days, period_interval=args.interval
    )
    result = backtest(histories)
    report = result.metrics().as_dict()
    report["n_markets"] = result.n_markets
    report["elapsed_s"] = round(time.time() - started, 1)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
