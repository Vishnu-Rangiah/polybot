# Task Split: Kalshi Autoresearch Agent

This file coordinates team work. The canonical design lives in `docs/DESIGN.md`.

## Current Priority

Build the live Python terminal weather-market MVP first, then add the frozen backtester and autoresearch loop if time allows.

## Team Tracks

Two tracks can run in parallel once the shared contract is agreed.

```text
Person A: Quant/Data
  Owns historical data, backtesting, metrics, and anti-overfitting rigor.

Person B: Agent/Integration
  Owns live terminal agent, Kalshi/NWS integration, reports, loop, and demo polish.
```

## 0. Together First: Lock The Contract

Put these definitions in `src/kalshi_agent/types.py`.

- [ ] Define `MarketState`.
- [ ] Define `Order`.
- [ ] Define `Metrics`.
- [ ] Agree that `strategy.py` exposes `decide(state: MarketState) -> Order | None`.
- [ ] Agree that `backtest(strategy_fn, *, split: str) -> Metrics` is the frozen scorer contract.
- [ ] Decide provisional train/val/test date boundaries once historical data availability is known.

## 1. Live Weather MVP

Owner: Agent/Integration.

Goal: terminal command that researches one live Kalshi weather market and prints a paper-trade memo.

- [ ] Create Python package skeleton under `src/kalshi_agent/`.
- [ ] Add minimal `requirements.txt`, starting with `requests`.
- [ ] Implement `kalshi_client.py` for public market and orderbook endpoints.
- [ ] Implement `pricing.py` to infer `yes_ask` and `no_ask` from YES/NO bids.
- [ ] Implement `rule_parser.py` for NYC rain and one high-temperature market.
- [ ] Implement `nws_client.py` with required NWS `User-Agent`.
- [ ] Implement `weather_model.py` with transparent rain/high-temperature heuristics.
- [ ] Implement `decision.py` for fee/slippage/liquidity-adjusted paper decisions.
- [ ] Implement `report.py` for terminal JSON and human-readable memo output.
- [ ] Implement `cli.py` so the demo can run with `python -m kalshi_agent.cli --ticker <ticker>`.
- [ ] Add fixture mode for demo reliability if live APIs fail.

## 2. Quant/Data Track

Owner: Quant/Data.

Goal: build the credibility layer behind the live agent.

### 2.1 Kalshi Data Pipeline

- [ ] Confirm Kalshi historical data endpoints and auth requirements.
- [ ] Confirm how far back price/orderbook history goes.
- [ ] Confirm rate limits.
- [ ] Pull resolved weather markets with known outcomes.
- [ ] Pull or reconstruct price history when possible.
- [ ] Cache data under `data/cache/`.
- [ ] Split by resolution date into train, val, and test.

### 2.2 Frozen Backtester

This is the core IP.

- [ ] Implement `backtest.py` with `backtest(strategy_fn, *, split: str) -> Metrics`.
- [ ] Enforce no-lookahead: at decision time `t`, strategies see only data with timestamp `< t`.
- [ ] Fill buys at ask and sells at bid.
- [ ] Include slippage and liquidity caps from recorded depth when available.
- [ ] Include Kalshi fee estimates.
- [ ] Return `pnl`, `sharpe`, `brier`, `n_trades`, and `max_dd`.
- [ ] Ensure the agent cannot edit `backtest.py` once the loop exists.

### 2.3 Baseline Strategy

- [ ] Add a simple `strategy.py` that consumes `MarketState`.
- [ ] Confirm it runs through the backtester on train, val, and test.
- [ ] Add at least one weather-based strategy using NWS probability features.

### 2.4 Overfitting Demo Beat

- [ ] Create an intentionally overfit strategy that scores well on train.
- [ ] Show that it fails on val/test.
- [ ] Use this as the proof that the frozen scorer is honest.

## 3. Agent / Autoresearch Track

Owner: Agent/Integration.

Goal: make the agent iterate on strategies without compromising the scorer.

### 3.1 Thesis File

- [ ] Create `thesis.md`.
- [ ] Describe market regime, edge hypothesis, and allowed strategy features.
- [ ] Include guardrails: pure function only, no edits to `backtest.py`, no external secret access.

### 3.2 Loop Driver

- [ ] Create `loop.py`.
- [ ] Read `thesis.md`.
- [ ] Ask the agent to edit only `strategy.py`.
- [ ] Run `backtest()` on train and val.
- [ ] Append every attempt to `ledger.json`.
- [ ] Keep a strategy only if validation improves under the agreed rule.
- [ ] Start against a mocked `backtest()` if the real scorer is not ready.

Keep/discard rule:

```text
Keep iff val.sharpe beats rolling best
AND val.brier does not degrade
AND n_trades >= N_min
```

### 3.3 Raindrop Workshop

Stretch goal for special prize.

- [ ] Install and wire Raindrop Workshop.
- [ ] Emit one trace per autoresearch iteration.
- [ ] Include thesis read, strategy edit, backtest call, metrics, and keep/discard decision.
- [ ] Define keep/discard as an eval.

## 4. Integration

Together.

- [ ] Swap mocked `backtest()` for real `backtest.py`.
- [ ] Run the loop over train and val.
- [ ] Run the final chosen strategy on test exactly once.
- [ ] Save final metrics for the demo.
- [ ] Dry-run demo script end to end.

## 5. Demo Checklist

- [ ] Terminal command works for one live weather ticker.
- [ ] Output includes market, rule summary, orderbook snapshot, model probability, edge, decision, risks, and sources.
- [ ] Backup fixture mode works without network.
- [ ] `docs/DESIGN.md` explains the architecture.
- [ ] `docs/TASKS.md` shows team coordination.
- [ ] If available, ledger/backtest output shows rigor.
- [ ] If available, Raindrop trace shows agent loop.

## Cutline If Short On Time

Do not cut the live weather terminal demo.

Cut in this order:

1. Raindrop tracing.
2. Live paper-trade outer loop.
3. Full autoresearch loop.
4. Full historical backtester.

Do not cut:

- Market/orderbook fetching.
- NWS retrieval.
- Paper-only guardrail.
- Human-readable output.
- Explicit risk flags.
