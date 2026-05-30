# Task Split — Autoresearch Trading

Two tracks. **Person A = Quant/Data** (owns the frozen scorer — the core IP).
**Person B = Agent/Integration** (owns the loop, Raindrop, live demo).

The only hard dependency is the **shared contract** below. Lock it first, then both
tracks run in parallel against stubs until integration.

---

## 0. Together first (~30 min) — lock the contract

These three type definitions are the seam between the two tracks. Put them in `types.py`.

- [ ] `MarketState` — what `decide()` can see at time `t` (yes/no price, recent history,
      volume, time-to-resolution, series/category, precomputed features).
- [ ] `Order` — side (yes/no), size, limit price. `None` = no trade.
- [ ] `Metrics` — `pnl, sharpe, brier, n_trades, max_dd`.
- [ ] `backtest(strategy_fn, *, split) -> Metrics` signature agreed.
- [ ] Decide train/val/test date boundaries (depends on how far Kalshi history goes —
      A confirms in A1, but pick provisional dates now so B can mock).

Once this is committed, A and B never block each other until §3.

---

## Person A — Quant / Data track

### A1. Kalshi data pipeline — `data/fetch.py`  — **owner: Andrew**
- [ ] Confirm Kalshi API: auth (RSA key signing), rate limits, **how far back price
      history goes** (this bounds the splits — report back to B).
- [ ] Pull a few hundred **resolved** markets (have known outcomes) + their price history.
- [ ] Cache to `data/cache/` (parquet/json) so we never refetch during iteration.
- [ ] Split by **resolution date** into train / val / test. Persist the split.

### A2. The frozen scorer — `backtest.py`  ← **most important file in the project**  — **owner: Vishnu**
- [ ] Implement `backtest(strategy_fn, split)` that replays markets chronologically.
- [ ] **No lookahead**: at decision time `t`, only feed data with timestamp `< t`.
- [ ] Frictions: fill at ask/bid spread, slippage + liquidity cap from recorded depth,
      Kalshi fee schedule. (A frictionless backtest is fiction on thin markets.)
- [ ] Compute all five metrics. Return one `Metrics` struct.

### A3. Baseline strategy — `strategy.py` (the seed the agent will mutate)
- [ ] Write one trivial `decide()` (e.g. buy yes if price < 0.5 and trending up).
- [ ] Confirm it runs end-to-end through `backtest()` on all three splits.

### A4. Overfitting demo beat (proof the gate works)
- [ ] Hand-craft an obviously overfit strategy that scores great on `train` and dies on
      `test`. This is the moment in the demo that proves our rigor — own it.

---

## Person B — Agent / Integration track

### B1. Agent loop — `loop.py`  ← the autoresearch engine
- [ ] Driver: read `thesis.md` → ask the agent to edit `strategy.py` → run `backtest()`
      on train+val → append result to `ledger.json` → keep/discard → repeat.
- [ ] Keep/discard rule: keep iff `val.sharpe` beats rolling-best AND `val.brier`
      doesn't degrade AND `n_trades ≥ N_min`.
- [ ] Maintain `ledger.json` (append-only: every attempt + best-so-far = our "checkpoint").
- [ ] Build against a **mocked `backtest()`** until A2 lands (returns fake Metrics).

### B2. `thesis.md` — the steering wheel
- [ ] Write the agent-facing prompt/instructions: market regime + edge hypothesis +
      guardrails (must return a pure function, must not edit `backtest.py`).

### B3. Raindrop Workshop integration (special prize)
- [ ] Install Workshop, wire tracing so each iteration emits a trace
      (thesis read → edit → backtest call → metrics).
- [ ] Define the keep/discard as a Raindrop **eval** (beat rolling-best val Sharpe w/o
      degrading Brier). This is the "coolest use case" hook.

### B4. Live paper-trade (outer loop) + demo
- [ ] Take the winning strategy and run it against Kalshi **demo/paper** env live.
- [ ] Wrap the demo narrative: show the overnight ledger + a Raindrop trace timeline +
      one live paper trade. (Live trade is NOT in the optimization loop — keep it separate.)

---

## §3. Integration (together, end of build)
- [ ] Swap B's mocked `backtest()` for A's real one. Run the real overnight loop.
- [ ] Run the final number on `test` **once**. That's the headline metric.
- [ ] Dry-run the demo: overfit-fails-on-test beat → real loop ledger → Raindrop → live trade.

---

## Critical-path notes
- A1 → A2 → A4 is the longest chain; A should start immediately, B can mock around it.
- The walk-forward split (§0 + A1) is load-bearing. If the agent ever sees the data it's
  scored on, the whole demo is a lie that looks great. Guard it.
- If short on time, cut B4 (live trade) before cutting A2 frictions or the overfit demo.
