# Autoresearch for Prediction-Market Trading

**One line:** Give an agent a frozen backtester and a mutable strategy file, and let it
do quantitative trading research overnight — propose a hypothesis, write the algorithm,
backtest it on held-out market history, keep the winners, discard the losers, repeat.

This is [karpathy/autoresearch](https://github.com/karpathy/autoresearch) with the ML
training loop swapped for a trading research loop, targeting **Kalshi** (US-regulated,
CFTC, no VPN needed).

---

## 1. The thesis: training a model ≈ researching a strategy

| ML training (autoresearch)        | Strategy research (this project)                  |
|-----------------------------------|---------------------------------------------------|
| `program.md` — research direction | `thesis.md` — market regime + edge hypothesis     |
| edit `train.py` (the model)       | edit `strategy.py` (signal → position)            |
| train for 5 min                   | backtest over historical Kalshi markets           |
| `val_bpb` on a **held-out** set   | Sharpe / PnL / Brier on an **out-of-sample** window |
| keep-or-discard, repeat           | keep-or-discard, repeat                            |
| final checkpoint → deploy         | final strategy → paper-trade → live               |

The insight we are copying is **not** "an LLM can trade." It is that autonomous iteration
only converges when the harness is rigged correctly:

1. **One mutable artifact** the agent edits (`strategy.py`).
2. **One frozen scorer** the agent *cannot* touch (`backtest.py`).
3. **One comparable metric** per run, on data the agent never optimized against.
4. **A split that punishes memorization** (walk-forward in time).

> The frozen scorer is the core IP. In ML, overfitting only costs val loss. In trading,
> overfitting costs real money *and looks identical to a winning strategy in-sample*.
> The whole project's credibility lives in the backtester's honesty.

---

## 2. Two loops, not five steps

The user-facing pipeline has five stages, but they belong to two different loops:

```
INNER LOOP  (automated, runs overnight — this is the autoresearch part)
  thesis  →  algorithm  →  backtest  →  metric  →  keep / discard  ┐
     ↑                                                              │
     └──────────────────── iterate ────────────────────────────────┘

OUTER LOOP  (human-gated, not overnight)
  best strategy  →  implementation (paper trade)  →  evals (forward test on new markets)
```

- **Inner loop** is what we build and demo. It is cheap, fast, and fully comparable.
- **Outer loop** is the "deploy the checkpoint" step. We will paper-trade the winning
  strategy live against Kalshi to make the demo tangible, but it is *not* in the
  optimization loop (that would leak the future into training).

---

## 3. Repository layout

```
autoresearch-trading/
├── thesis.md            # MUTABLE by human — steering wheel for the agent
├── strategy.py          # MUTABLE by agent — the only artifact it edits
├── backtest.py          # FROZEN — the honest scorer; agent must never edit
├── data/
│   ├── fetch.py         # pulls + caches resolved Kalshi markets via API
│   └── cache/           # parquet/json of historical markets, pre-split by time
├── loop.py              # the agent driver: read thesis → edit → backtest → log → decide
├── ledger.json          # append-only record of every attempt + best-so-far
└── raindrop/            # eval definitions for Raindrop Workshop (see §7)
```

Mirror of autoresearch: `backtest.py` ≈ `prepare.py` (frozen), `strategy.py` ≈ `train.py`
(mutable), `thesis.md` ≈ `program.md`, `loop.py` ≈ the overnight runner.

---

## 4. The frozen scorer — `backtest.py`

This is the most important file. Its contract:

```python
def backtest(strategy_fn, *, split: str) -> Metrics:
    """Run strategy_fn over the requested time split and return one comparable result.
    split ∈ {"train", "val", "test"}. The agent may run "train" freely;
    the keep/discard decision is made ONLY on "val". "test" is touched once, at the end.
    """
```

Non-negotiable realism (prediction markets are thin — a frictionless backtest is fiction):

- **Spread**: fill at the ask when buying / bid when selling, from recorded order book.
- **Slippage + liquidity cap**: size is bounded by recorded depth; large orders walk the book.
- **Fees**: Kalshi's trading fee schedule baked in.
- **No lookahead**: at decision time `t`, the strategy sees only data with timestamp `< t`.
  Resolution outcomes are revealed only after the market closes.

### Metrics returned (one struct, a few scalars)

| metric        | what it measures                  | why it's here                          |
|---------------|-----------------------------------|----------------------------------------|
| `pnl`         | realized $ over the split         | the obvious objective                  |
| `sharpe`      | risk-adjusted return              | punishes lucky high-variance bets      |
| `brier`       | mean squared prob error (calibration) | keeps probabilistic edge honest    |
| `n_trades`    | sample size                       | guards against "1 lucky trade" winners |
| `max_dd`      | max drawdown                      | survivability                          |

Keep/discard rule (start simple, tune later): **keep iff `val.sharpe` beats rolling best
AND `val.brier` does not degrade AND `n_trades ≥ N_min`.**

> Requiring `n_trades ≥ N_min` is the trading version of a minimum batch size: it stops
> the agent from "winning" on a sample too small to mean anything.

---

## 5. The mutable artifact — `strategy.py`

A single pure function the agent rewrites each iteration:

```python
def decide(market_state: MarketState) -> Order | None:
    """Given everything observable about a market at time t, return an order or None.
    market_state: current yes/no prices, recent price history, volume, time-to-resolution,
                  series/category, and any features fetch.py precomputed.
    Order: side (yes/no), size, limit price.
    """
```

Keeping it a pure function of observable state is what makes the no-lookahead guarantee
*structural* rather than a thing we hope the agent respects.

---

## 6. Walk-forward split (the anti-overfitting gate)

Split resolved markets by **resolution date**, not randomly:

```
|—— train ——|—— val ——|—— test ——|
   Jan–Mar     Apr–May    Jun
   agent       keep/      touched
   optimizes   discard    once, ever
   here        decided    at the end
               here
```

The agent only ever sees `train`. The keep/discard judge reads `val`. `test` is opened a
single time for the final number we report — touch it more and it stops being out-of-sample.

> This is the single most important design decision in the whole project. If the agent can
> see the data it's scored on, it will overfit and the demo will be a lie that looks great.

---

## 7. Raindrop Workshop integration (special prize)

[Raindrop Workshop](https://github.com/raindrop-ai/workshop) is a local trace viewer +
self-healing eval loop for agents. Fit:

- **Each iteration is a trace**: thesis read → strategy edit → backtest call → metrics.
  Workshop streams the overnight research run as a live span timeline.
- **Keep/discard becomes a Raindrop eval**: "did this iteration beat rolling-best val
  Sharpe without degrading Brier?" — exactly their eval pattern, but graded on
  money-grounded metrics instead of chat quality.
- **The pitch**: "coolest use case" = evaluating an agent's *research output* with real PnL
  and calibration, not its prose.

---

## 8. Kalshi specifics (verify against live API docs before coding)

- US-regulated, USD, REST API at `api.elections.kalshi.com` / `trading-api.kalshi.com`.
- Useful endpoints to confirm: markets list, market history/candlesticks, order book,
  event/series metadata. Demo (paper) environment exists for the outer-loop live step.
- Historical resolved markets give us labeled outcomes for backtesting for free.
- **Action item:** confirm rate limits, auth (API key / RSA signing), and how far back
  price history goes — that bounds how big the train/val/test windows can be.

---

## 9. Build order

1. `data/fetch.py` — pull + cache a few hundred resolved markets, split by date. *(prove data)*
2. `backtest.py` — frozen scorer with frictions + the three metrics. *(the core IP)*
3. `strategy.py` — a trivial baseline (e.g. "buy yes if price < 0.5 and trending up").
4. `loop.py` — agent driver: read thesis, edit strategy, backtest on train+val, log to
   ledger, keep/discard. *(the autoresearch loop)*
5. Raindrop wiring — emit traces + eval per iteration.
6. Outer loop — paper-trade the winner against Kalshi demo env for the live demo.

---

## 10. Risks & honest caveats

- **Overfitting** is the default failure. Mitigated by walk-forward + Brier + `n_trades` floor.
  We should *show* an overfit run failing on `test` as proof the gate works — it's a great demo beat.
- **Thin liquidity** means in-sample PnL is optimistic; frictions in `backtest.py` are our defense.
- **Data depth**: if Kalshi history is shallow, windows shrink and variance rises. Confirm in step 1.
- **Edge is hard**: markets are roughly efficient. The win condition for the hackathon is a
  *credible research loop*, not beating the market — though calibration edge on thin markets is plausible.
