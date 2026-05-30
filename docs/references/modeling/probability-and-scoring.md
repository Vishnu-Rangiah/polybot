# Probability, Edge & Scoring — Reference

Conceptual reference for the two numbers this project keeps producing: a **fair
probability** for a market, and a **score** for how good those probabilities turned
out to be. Authored for the repo (not scraped); formulas are standard. Pair with
`../kalshi/rate-limits-and-fees.md` (fees) and `../kalshi/orderbook.md` (prices).

---

## 1. Prices are probabilities (with frictions on top)

A Kalshi YES contract pays $1.00 if the event happens, $0.00 otherwise. So a YES
price of `p` dollars is the market's implied probability, **before** fees and spread:

```
implied_P(yes) ≈ yes_price            # e.g. 0.37 -> ~37%
implied_P(no)  ≈ no_price  = 1 - yes_price
```

But you don't trade at one price — you cross a spread, and the book is bids-only:

```
yes_ask = 1 - best_no_bid      # what you PAY to buy YES
yes_bid = best_yes_bid         # what you RECEIVE to sell YES
mid     = (yes_bid + yes_ask) / 2
```

Use **mid** as the market's "consensus" probability for analysis, but always size and
evaluate edge against the **ask you'd actually cross**, never the mid. Confusing mid
with executable price is the most common way a paper edge evaporates live.

---

## 2. Fair value → edge → expected value

Let `fair_p` be your model's probability the event resolves YES.

**Raw edge** (ignoring fees) for each side:

```
edge_yes = fair_p        - yes_ask     # buy YES if your prob exceeds the ask
edge_no  = (1 - fair_p)  - no_ask      # buy NO  if your prob of NO exceeds its ask
```

**Expected value per contract, after fees.** A YES contract bought at `yes_ask`
costs `yes_ask + fee` and returns $1 with prob `fair_p`:

```
EV_yes = fair_p * (1 - yes_ask) - (1 - fair_p) * yes_ask - fee
       = fair_p - yes_ask - fee
```

So **trade only when `fair_p - yes_ask > fee`** (and symmetrically for NO). The fee is
the round-up-to-the-cent parabolic charge in `../kalshi/rate-limits-and-fees.md`;
it is largest near `0.50` and shrinks toward the tails — which is exactly where many
weather buckets sit, so it bites. A 2–3¢ apparent edge can be entirely fee + spread.

**Minimum edge rule of thumb:** require `edge > fee + half_spread + margin`, where
`margin` covers model error and settlement risk. Be honest about `margin`; an
overconfident model with a tiny nominal edge is a losing trade.

---

## 3. Turning a forecast into a bucket probability

Weather markets are bucketed (e.g. high temp `70–71°F`). A point forecast alone is
not a probability — you need a distribution around it.

1. **Get a central estimate** `mu` (e.g. NWS/Open-Meteo forecast high for the
   settling station — see `../kalshi/weather-markets.md` for which station).
2. **Attach an error distribution.** Model forecast error as roughly Normal with a
   standard deviation `sigma` estimated from history (forecast vs. realized at that
   lead time). Same-day highs might have `sigma ≈ 1–2°F`; multi-day leads widen it.
3. **Integrate over the bucket.** For a bucket `[lo, hi)`:

   ```
   P(bucket) = Phi((hi - mu)/sigma) - Phi((lo - mu)/sigma)
   ```

   where `Phi` is the standard Normal CDF. Open-ended tail buckets use one side only.
4. **Normalize** across the event's mutually-exclusive buckets so they sum to 1.
5. **Rain markets** are a single binary: convert PoP / realized-precip history into
   `P(precip > 0")` at the settling station, remembering Trace counts as YES.

The `sigma` is doing the real work. A too-small `sigma` makes you overconfident on the
center bucket and you'll overpay; calibration (below) is how you check it.

---

## 4. Scoring probabilistic predictions

These are the metrics DESIGN.md uses to grade strategies. All operate on pairs of
(forecast probability `p_i`, realized outcome `o_i ∈ {0,1}`).

### Brier score (primary)

Mean squared error of probabilities. **Lower is better**; range `[0, 1]`.

```
Brier = (1/N) * Σ (p_i - o_i)^2
```

- Always-0.5 forecaster scores 0.25 — that's the "know nothing" baseline to beat.
- Perfect, confident, correct forecaster scores 0.
- Penalizes both miscalibration and lack of sharpness in one number.

### Log loss (a.k.a. cross-entropy)

```
LogLoss = -(1/N) * Σ [ o_i*ln(p_i) + (1-o_i)*ln(1-p_i) ]
```

Harsher than Brier on confident wrong calls — a `p=0.99` that resolves NO is
catastrophic (it's `ln(0.01)`). **Clip** `p` to `[ε, 1-ε]` (e.g. `ε=1e-6`) so a single
0/1 doesn't produce infinity. Use it when overconfidence is the failure you most fear.

### Calibration (reliability)

Bucket predictions by probability (e.g. 0–10%, 10–20%, …) and compare the average
forecast in each bin to the empirical hit rate. A **calibrated** model's curve lies on
the diagonal: of all the times you said "30%", ~30% happened.

```
ECE = Σ_bins (n_bin/N) * | mean_forecast_bin - empirical_rate_bin |
```

Calibration ≠ accuracy. A model can be perfectly calibrated and useless (always
predicts the base rate), or sharp but miscalibrated (right ranking, wrong levels).
You want **both**: calibrated *and* sharp. Brier decomposes into exactly that:
`Brier = reliability − resolution + uncertainty`.

### Trading metrics (the ones that pay)

Probability scores grade the *model*; these grade the *strategy* (DESIGN.md lists
PnL, Sharpe, Brier, n_trades, max drawdown):

- **PnL** — realized profit, net of fees and the spread you crossed. The only metric
  that's real money.
- **Sharpe** — mean per-trade PnL ÷ its standard deviation. Rewards consistency, not
  one lucky settlement. With few trades it's noisy — report `n_trades` alongside.
- **Max drawdown** — worst peak-to-trough equity drop. A high-Sharpe strategy with a
  ruinous drawdown is still untradeable.
- **n_trades** — sample size. A 0.30 Brier over 12 trades tells you almost nothing;
  guard every metric with its sample count.

---

## 5. Position sizing (brief)

Given an edge, the Kelly fraction for a binary at price `c` with fair prob `p`:

```
f* = (p - c) / (1 - c)          # fraction of bankroll on YES, when p > c
```

In practice use **fractional Kelly** (e.g. ¼ to ½ of `f*`): full Kelly assumes your
`p` is exactly right, and on prediction markets it isn't. Model error, correlated
positions (many weather markets share a front), and settlement risk all argue for
sizing down. The MVP is paper-trade only — sizing is for after evals and risk limits
exist (DESIGN.md), so treat this section as the target, not day-one behavior.

---

## 6. Pitfalls specific to this project

- **In-sample calibration lies.** A model tuned on the same data it's scored on looks
  calibrated and overfits. Hold out a frozen test split the agent never sees — this is
  the whole point of the autoresearch frozen backtester
  (`../autoresearch/README.md`).
- **Lookahead via the forecast.** When backtesting, use the forecast that was
  available *before* decision time `t`, not the realized value or a later forecast.
  The Open-Meteo *archive* gives you realized weather — great for settling, poison if
  it leaks into the features. See `../weather/open-meteo.md`.
- **Scoring against the wrong source.** Grade against the actual settlement number
  (the CLI report / named station), not ERA5 grid or a nearby station. A
  well-calibrated model against the wrong truth is a confidently wrong model.
- **Edge inside the fee.** Re-check every signal: is the edge bigger than fee + half
  the spread? Near 0.50 the fee alone can exceed a 2¢ edge.
- **Survivorship / selection.** If you only backtest markets that stayed liquid or
  only days you had forecasts for, your metrics are optimistic. Log what you dropped.
