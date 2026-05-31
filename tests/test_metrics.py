"""Metrics tests: closed-form checks for the scorecard and the fee model.

Pure functions with known answers — no network, no fixtures beyond hand-built
records. If these drift, every backtest number drifts with them.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_agent.metrics import (
    brier,
    kalshi_fee_cents,
    pnl_cents,
    summarize,
    win_rate,
)
from kalshi_agent.types import ClosedTrade, Prediction, Side


def _trade(entry: int, settle: int, *, qty: int = 1, fee: int = 0) -> ClosedTrade:
    return ClosedTrade(
        ticker="T", side=Side.YES, quantity=qty,
        entry_cents=entry, fee_cents=fee, settle_cents=settle,
    )


def _pred(p: float, outcome: int) -> Prediction:
    return Prediction(ticker="T", observed_at_ms=0, fair_prob_yes=p, outcome=outcome)


def test_pnl_accounts_for_payout_cost_and_fees():
    # 10 contracts bought at 40c, settled at 100c, 2c fees -> 10*(100-40) - 2.
    trade = _trade(40, 100, qty=10, fee=2)
    assert trade.pnl_cents() == 598
    assert pnl_cents([trade]) == 598


def test_win_rate_counts_positive_trades():
    winner = _trade(40, 100)   # +60
    loser = _trade(60, 0)      # -60
    assert win_rate([winner, loser]) == 0.5
    assert win_rate([]) == 0.0


def test_brier_is_mean_squared_error():
    # (0.8-1)^2 = 0.04 ; (0.3-0)^2 = 0.09 ; mean = 0.065.
    score = brier([_pred(0.8, 1), _pred(0.3, 0)])
    assert score is not None and math.isclose(score, 0.065)


def test_brier_is_none_when_nothing_priced():
    assert brier([]) is None


def test_kalshi_fee_peaks_at_midprice_and_vanishes_at_extremes():
    # ceil(0.07 * 1 * 0.5 * 0.5 * 100) = ceil(1.75) = 2.
    assert kalshi_fee_cents(1, 50) == 2
    # p = 1.0 -> P*(1-P) = 0 -> no fee.
    assert kalshi_fee_cents(1, 100) == 0
    # fee scales with quantity.
    assert kalshi_fee_cents(10, 50) == math.ceil(0.07 * 10 * 0.25 * 100)


def test_summarize_combines_everything():
    m = summarize([_trade(40, 100, fee=2)], [_pred(0.8, 1)])
    assert m.pnl_cents == 58
    assert m.n_trades == 1
    assert m.win_rate == 1.0
    assert m.brier is not None and math.isclose(m.brier, 0.04)
    assert m.n_predictions == 1
    assert m.as_dict()["pnl_dollars"] == 0.58


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
