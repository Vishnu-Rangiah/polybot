# autoresearch — reference & adaptation note

A cleaned copy of [karpathy/autoresearch](https://github.com/karpathy/autoresearch)
(MIT, `master` @ 2026-03-26). We vendored the **methodology**, not the code:

- `program.md` — the agent's autonomous experiment loop (verbatim). The core artifact.
- `upstream-README.md` — Karpathy's README: the philosophy and design choices.

**Dropped on purpose:** `train.py`, `prepare.py`, `analysis.ipynb`, `pyproject.toml`.
Those are a single-GPU nanochat LLM-training setup — irrelevant to prediction
markets. The whole point of autoresearch is that the *loop* is domain-agnostic; the
training code is just the example domain Karpathy happened to use. Get the full repo
from the upstream link if you ever want it.

## Why this is in our repo

Our `../../DESIGN.md` Phase 2 is autoresearch applied to trading:

> Give an agent one mutable `strategy.py` and a frozen `backtest.py`; let it iterate
> on strategies while validation metrics prevent overfitting.

That is structurally identical to what `program.md` describes. The mapping:

| autoresearch (nanochat) | our Kalshi project |
|---|---|
| `train.py` — the **one file the agent edits** | `strategy.py` — agent edits only this |
| `prepare.py` — frozen data/eval harness | `backtest.py` — frozen, no-lookahead scorer |
| metric: `val_bpb` (lower better) | metric: backtest val score (e.g. PnL / Sharpe) |
| fixed 5-min wall-clock budget per run | one backtest run over a fixed train/val split |
| `results.tsv` keep/discard log | strategy ledger of kept/discarded experiments |
| branch `autoresearch/<tag>` per run | branch per research session |

The keep/discard engine is the same: **mutate → run frozen eval → compare metric →
keep (advance branch) or discard (git reset) → repeat.** `program.md` is the
battle-tested prompt for that engine — read it before writing our own `program.md`.

## What to borrow directly

From `program.md`, these transfer to our backtester with almost no change:

- **Frozen eval is ground truth.** The agent may never edit `backtest.py`, exactly
  as it may never edit `prepare.py`. This is what makes results trustworthy and is
  our defense against the agent "winning" by editing the scorer.
- **Keep/discard via git.** Advance the branch on improvement, `git reset` on
  regression. Cheap, reviewable, reversible.
- **Append-only results log.** One row per experiment: commit, metric, status,
  one-line description. Tab-separated, untracked by git.
- **Simplicity criterion.** A tiny metric gain that adds ugly complexity is not
  worth it; a simplification that holds the metric is a win.
- **Never stop.** The loop runs until a human interrupts.

## What we must change (the trading-specific risk)

autoresearch optimizes one clean metric with no real-world downside. Markets punish
that naivety, so layer on top of the loop:

- **No-lookahead is non-negotiable.** `strategy_fn` sees only data available before
  decision time `t`. autoresearch never has to worry about leakage; we do.
- **Hold out a test split.** Score on train+val during the loop, keep a frozen test
  split the agent never sees, to catch overfitting (DESIGN.md's "overfit strategy
  scores well on train, fails on test" demo).
- **Bake in frictions.** Fees, spread, slippage, thin liquidity must be inside
  `backtest.py` or the metric lies. See `../kalshi/rate-limits-and-fees.md` and
  `../kalshi/orderbook.md`.
- **Paper-trade before live.** A high backtest score is a hypothesis, not a proven
  edge. No real money until evals + risk limits + manual approval exist.
