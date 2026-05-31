"""Evaluation: turn a backtest's records into a handful of honest numbers.

Two families of signal, deliberately kept separate:

  - economic  (did the *strategy* make money):   pnl, n_trades, win_rate
  - probabilistic (is the *model* any good):      brier

Brier is scored over every market the model priced — even ones the strategy
chose not to trade — so a well-calibrated model hidden behind a too-tight trade
gate still shows up as good. That separation is the core diagnostic for
iterating on a hypothesis: "good model, bad gate" vs. "miscalibrated model".

Everything here is pure (records in, numbers out). `summarize` is the one-call
entry point the backtester uses.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from kalshi_agent.types import ClosedTrade, Prediction


@dataclass(frozen=True, slots=True)
class Metrics:
    """The scorecard for one backtest run."""

    pnl_cents: int
    n_trades: int
    win_rate: float  # fraction of trades with positive realized P&L
    brier: float | None  # mean((fair_prob_yes - outcome)^2); None if nothing priced
    n_predictions: int

    def as_dict(self) -> dict:
        """JSON-friendly view — what an agent tool or CLI prints."""
        return {
            "pnl_cents": self.pnl_cents,
            "pnl_dollars": round(self.pnl_cents / 100, 2),
            "n_trades": self.n_trades,
            "win_rate": round(self.win_rate, 4),
            "brier": None if self.brier is None else round(self.brier, 4),
            "n_predictions": self.n_predictions,
        }


def pnl_cents(trades: Sequence[ClosedTrade]) -> int:
    """Total realized P&L across all closed trades, in cents."""
    return sum(t.pnl_cents() for t in trades)


def win_rate(trades: Sequence[ClosedTrade]) -> float:
    """Fraction of trades that finished positive. 0.0 when there are no trades."""
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.pnl_cents() > 0)
    return wins / len(trades)


def brier(predictions: Sequence[Prediction]) -> float | None:
    """Brier score: mean squared error of the model probability vs. the outcome.

    0 is perfect, 0.25 is the score of always guessing 0.5, 1 is worst. Returns
    None when no predictions were made, so an empty run reads as "no signal"
    rather than a misleadingly perfect 0.
    """
    if not predictions:
        return None
    return sum((p.fair_prob_yes - p.outcome) ** 2 for p in predictions) / len(predictions)


def kalshi_fee_cents(quantity: int, price_cents: int, *, multiplier: float = 0.07) -> int:
    """Kalshi trading fee for a fill: ceil(multiplier * C * P * (1 - P)) in cents.

    P is the price in dollars (price_cents / 100). The fee peaks near 50c (max
    uncertainty) and vanishes toward 0/100c. 0.07 is the standard exchange
    multiplier; a few series differ, but it is the right default. Rounded *up* to
    whole cents — the exchange never rounds a real fill's fee down to zero.

    Why this matters: on weather markets the fee and spread routinely exceed the
    apparent edge, so a fee-free backtest systematically overstates profitability.
    """
    p = price_cents / 100.0
    return math.ceil(multiplier * quantity * p * (1.0 - p) * 100)


def summarize(
    trades: Sequence[ClosedTrade], predictions: Sequence[Prediction]
) -> Metrics:
    """Collapse a run's trade + prediction records into a single `Metrics`."""
    return Metrics(
        pnl_cents=pnl_cents(trades),
        n_trades=len(trades),
        win_rate=win_rate(trades),
        brier=brier(predictions),
        n_predictions=len(predictions),
    )
