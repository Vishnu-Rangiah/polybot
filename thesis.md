# Strategy Search Thesis

This file is the instruction set for any agent (human or Codex) that proposes a new
Kalshi weather trading strategy. Read it fully before editing code.

## Goal

Find a paper-trading strategy that earns positive, risk-adjusted edge on Kalshi
weather markets after fees, spread, and slippage. The strategy must generalize:
it is scored on data it did not see, not just the data used to design it.

## What You May Edit

You may edit ONLY `strategy.py`.

You must keep this exact function contract:

```python
from kalshi_agent.autoresearch.types import MarketState, Order

def decide(state: MarketState) -> Order | None:
    ...
```

- Return an `Order` to take a paper position, or `None` to stand aside.
- `Order(side="yes" | "no", size=<positive int>, limit_price=<float in 0..1>)`.
- The function must be pure: same `state` in, same decision out. No file writes,
  no network calls, no randomness, no reading of clocks or environment variables.

## What You May NOT Touch

Do not edit, import-patch, or otherwise depend on changing these:

- `kalshi_agent/autoresearch/backtest.py` (the frozen scorer)
- `kalshi_agent/autoresearch/evaluator.py` (eval + promotion gate)
- `kalshi_agent/autoresearch/registry.py` (candidate storage)
- `kalshi_agent/autoresearch/types.py` (shared contract)
- any cached market data or split definitions
- Kalshi credentials or any live trading code

The scorer runs after you exit and you cannot grade yourself.

## The Data You Get

Each decision sees one `MarketState` snapshot:

- `ticker`, `title`, `series_ticker`, `category`
- `yes_bid`, `yes_ask`, `no_bid`, `no_ask` (prices in 0..1, may be `None`)
- `volume`, `liquidity`, `time_to_close_seconds`
- `features`: a dict that may include
  - `market_family` (e.g. `weather_rain`, `weather_high_temp`)
  - `location` (e.g. `NYC`, `SFO`)
  - `model_probability_yes` (the research probability estimate, 0..1)
  - `resolution_ambiguity` (`low` | `medium` | `high`)

No-lookahead rule: you only ever see data available at decision time. You never
see the outcome. The backtester reveals outcomes only after your decision.

## Cost Model You Must Beat

The scorer fills buys at the ask, applies a Kalshi-style fee of
`ceil(0.07 * p * (1 - p) * 100) / 100` per contract, and applies slippage of
`0.02` when liquidity `< 100` else `0.01`. A naive "model probability minus ask"
edge often disappears after these costs, so account for them.

## How You Are Scored

The frozen backtester reports, per split: `pnl`, `sharpe`, `brier`, `n_trades`,
`max_dd`. Splits are `train`, `val`, and `test`.

- You may reason about `train`.
- Keep/discard is decided on `val`.
- `test` is touched only once, at the very end, and never to tune.

## Promotion Gate

A candidate is promoted to `promoted_paper` only if all hold on `val`:

- It compiles and preserves the `decide` contract.
- `n_trades` is at least the configured minimum (default 1).
- Validation `sharpe` strictly beats the current best promoted strategy.
- Validation `brier` does not degrade beyond the allowed margin (default 0.05).

Train performance alone never earns promotion. A strategy that wins on train but
fails on val is rejected on purpose.

## Good Directions To Try

- Require a minimum net edge after the cost model, not just a raw edge.
- Use `liquidity` and `resolution_ambiguity` as gates.
- Treat `weather_rain` and `weather_high_temp` differently if it helps.
- Consider standing aside (`None`) more often; fewer, higher-quality trades can
  improve Sharpe and Brier.

## Anti-Goals

- Do not overfit to specific tickers in the sample.
- Do not hardcode outcomes or ticker-to-result lookups.
- Do not widen size to inflate pnl without regard to drawdown.
