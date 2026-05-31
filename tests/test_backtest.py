"""Backtest tests: the end-to-end replay -> decide -> fill -> settle loop.

Built from synthetic MarketHistory (no network). Verifies a forced edge produces
the right trade and P&L, that the no-lookahead guard fires, that unsettled
markets are skipped, and that a missing model probability means no trade.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kalshi_agent.backtest import (
    BacktestConfig,
    MarketHistory,
    backtest,
    run_market,
)
from kalshi_agent.metrics import kalshi_fee_cents
from kalshi_agent.risk import RiskGate, RiskLimits
from kalshi_agent.types import MarketState, Settlement, Side


def _state(observed_at_ms: int, *, fair: float | None = 0.55, yes_ask: int = 40) -> MarketState:
    feats = {} if fair is None else {"fair_prob_yes": fair}
    return MarketState(
        ticker="KXRAINNYC-26MAY31-T0",
        observed_at_ms=observed_at_ms,
        yes_bid=yes_ask - 2, yes_ask=yes_ask,
        no_bid=100 - yes_ask, no_ask=100 - (yes_ask - 2),
        yes_bid_qty=100, no_bid_qty=100,
        features=feats,
    )


def _settled(result: str = "yes") -> Settlement:
    return Settlement(ticker="KXRAINNYC-26MAY31-T0", result=result, settled_ts=1717200000)


def _gate() -> RiskGate:
    return RiskGate(RiskLimits())


def test_forced_edge_produces_one_winning_trade():
    # One candle, fair 0.55 vs ask 40c -> buy YES; settles YES -> pays 100c.
    history = MarketHistory("KXRAINNYC-26MAY31-T0", [_state(1000)], _settled("yes"))
    trades, preds = run_market(history, _decide(), gate=_gate(), cfg=BacktestConfig())

    assert len(trades) == 1
    t = trades[0]
    assert t.side is Side.YES and t.entry_cents == 40 and t.settle_cents == 100
    fee = kalshi_fee_cents(1, 40)
    assert t.pnl_cents() == 1 * (100 - 40) - fee
    # one prediction joined to the realized YES outcome.
    assert len(preds) == 1 and preds[0].outcome == 1
    assert math.isclose(preds[0].fair_prob_yes, 0.55)


def test_losing_settlement_is_a_loss():
    history = MarketHistory("KXRAINNYC-26MAY31-T0", [_state(1000)], _settled("no"))
    trades, preds = run_market(history, _decide(), gate=_gate(), cfg=BacktestConfig())
    assert trades[0].settle_cents == 0
    assert trades[0].pnl_cents() < 0
    assert preds[0].outcome == 0


def test_non_monotonic_states_raise():
    history = MarketHistory(
        "KXRAINNYC-26MAY31-T0", [_state(2000), _state(1000)], _settled("yes")
    )
    try:
        run_market(history, _decide(), gate=_gate(), cfg=BacktestConfig())
    except ValueError as e:
        assert "lookahead" in str(e)
    else:
        raise AssertionError("expected ValueError on out-of-order states")


def test_no_model_probability_means_no_trade_and_no_prediction():
    history = MarketHistory(
        "KXRAINNYC-26MAY31-T0", [_state(1000, fair=None)], _settled("yes")
    )
    trades, preds = run_market(history, _decide(), gate=_gate(), cfg=BacktestConfig())
    assert trades == []
    assert preds == []


def test_backtest_skips_unsettled_markets():
    settled = MarketHistory("A", [_state(1000)], _settled("yes"))
    unsettled = MarketHistory(
        "B", [_state(1000)], Settlement(ticker="B", result="", settled_ts=None)
    )
    result = backtest([settled, unsettled])
    assert result.n_markets == 1  # only the settled one scored
    assert result.metrics().n_trades == 1


def _decide():
    """The project strategy, imported lazily so a typo here can't mask a real bug."""
    from kalshi_agent import strategy

    return strategy.decide


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
