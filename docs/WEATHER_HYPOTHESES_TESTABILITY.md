# Testability in a Codex + Modal Sandbox (historical data + outbound internet, nothing else)

Companion to `WEATHER_HYPOTHESES.md`. Grades each hypothesis on **can it be
backtested *now*, offline, with only historical data reachable from the sandbox** —
no forward data collection, no live trading, no order-flow capture.

## The one distinction that decides everything

Separate two questions, because they have very different data needs:

- **SIGNAL test** — "does my number beat the crowd's number?" (calibration: CRPS,
  Brier, reliability vs realized outcome). Needs only **forecast history + truth**.
  Both have *long* archives → testable far back.
- **TRADE test** — "would I have made money?" (realized EV vs the actual market
  price, net of fees, at fillable size). Needs **historical Kalshi prices** (1-min
  candlestick OHLC, ~months of history) and **depth** (Kalshi archives *none*).

So many hypotheses are **signal-testable on years of data but trade-testable only
on the recent candlestick window, with fill realism as a proxy.** Grades below
reflect both.

## The three hard data limiters (from the workflow's live probing)

1. **Per-member ensemble history ≈ 90 days.** Open-Meteo's ensemble historical only
   reaches ~2026-02-26 (AIFS). Per-member spread is *not* reconstructable further
   back. → The entire **ensemble-calibration family is signal-testable on ~90 days
   only, and trade-EV is not testable now** (needs forward-logging). Long-history
   alternative exists but is heavy: NOAA **AIWP reforecast** on AWS S3 (see H37).
2. **NBM / MOS / LAMP have no archive** (NOMADS ~2-day retention). → Any hypothesis
   keyed on NBM percentiles or MOS is **forward-collection only — not offline-testable**.
3. **IEM 1-min ASOS is lag-/gap-ridden** (KNYC flaky, returned 0 rows / `-1`).
   → Reconstruct the obs path from **hourly + SPECI METAR T-groups** (aviationweather
   /IEM METAR archive, tenths-°C, reliable) instead. Coarser cadence (~20-min, not
   1-min), so intraday metrics are defined on **obs-event windows**, not literal minutes.

Plus: **no historical orderbook depth** → fill/capacity is always a *proxy*
(top-of-book bid/ask from candlesticks + `volume_fp`), never queue-accurate.

---

## Grades

✅ **Testable now** · 🟡 **Partial** (signal yes / EV-or-window-limited) · ❌ **Not offline-testable** (forward-collection)

| # | Hypothesis | Grade | Binding data dependency | What Codex backtests offline |
|---|---|---|---|---|
| **H11** | LST/DST window correctness | ✅ | METAR/CLI history (both archived) | Deterministic, no fitting: fraction of DST-divergence days where LST-window max = CLI and civil-day max ≠ CLI (~100% if real). Highest-confidence test in the set. |
| **H7** | Running-Max Floor Engine | ✅ | METAR running-max path + candlesticks + CLI | Reconstruct running-max from hourly/SPECI METAR; below-floor buckets → fair 0; hit-rate ~100% by construction (a self-test of the settlement replicator) + lead-time staleness. |
| **H27b** | Post-Peak Lock convergence-gap | ✅ | daily running-max path + candlestick mids + CLI | Catalog states it explicitly needs *only* the daily running-max from hourly/SPECI METAR + CLI label. Win-rate ≥90%, gap captured at lock+15/60/120 min. Strongest survivor *and* fully testable. |
| **H10** | Responsiveness staleness screen | ✅ | 1-min candlesticks + obs-fair path + CLI | Reconstruct obs-fair path (METAR T-group), measure reaction-lag / idle-fraction / beta vs candlestick mid path; Spearman of prior-week staleness vs next-period realized edge. *Build first.* |
| **H14** | Tail-CDF monotonicity locks | ✅ | Kalshi ladder prices + CLI only (model-free) | Scan resolved ladders for executable survival-curve inversions on the C-derived F lattice; real-vs-phantom rate, realized locked payoff. No forecast/obs needed. |
| **H20** | Forecast→CLI station bias | ✅ signal / 🟡 EV | Open-Meteo Historical-Forecast (years) + IEM CF6 CLI | Rolling bias fit vs CLI is testable on *years* of deterministic forecast history (no ensemble). Trade-EV limited to candlestick window. |
| **H38** | Conditional UHI bias (KXLOW) | ✅ signal / 🟡 sample | Open-Meteo hist-forecast wind/sky/min + CLI low | Regression `residual ~ wind+cloud+season` testable on long deterministic history; **but <1 winter of calm-clear nights → overfit risk**; KXLOW price history thin/seasonal for EV. |
| **H9** | Settlement quantization replicator | ✅ model / 🟡 EV | METAR T-group (tenths-°C) + CLI; candlesticks | The C-round-then-convert chain is *validated against CLI* offline (does my quantizer reproduce the settled °F?). Trade-EV depends on rare edge-adjacent days with price history. |
| **H42** | Spread-compression rotate-out | ✅ | candlesticks (spread/quote-freq/vol/OI) + fill log | Venue-internal microstructure core needs no fair path; weekly metrics vs next-week realized edge. Needs *weeks* of candlestick history (exists/accrues). |
| **H39** | Multi-city correlation cap | ✅ | multi-city CLI history (long) + ensemble (90d) | Realized cross-city co-movement risk backtest on long CLI history; member-correlation input limited to 90d but the risk rule validates on outcomes. |
| **H18** | Stale-carryover at event open | 🟡 | candlesticks (price-reversion form ✅) / ensemble-gap form (90d) | Price-reversion-to-steady-state form is candlestick-only ✅; the "vs fresh ensemble PMF" form inherits the 90-day window. |
| **H1** | EMOS spread-scaled PMF | 🟡 signal-only | Open-Meteo `/v1/ensemble` (~90d) + CLI | Calibration (CRPS/PIT/rank-hist vs CLI) testable on ~90 days; **EV not testable now**. Also requires a bucket-PMF builder that doesn't exist in the repo yet. |
| **H5** | Ensemble-PMF ladder-shape RV | 🟡 | ensemble PMF (90d) + candlestick ladder | Testable only on the ~90-day ensemble∩candlestick overlap. |
| **H4** | Variance-regime selection | 🟡 | ensemble spread + Previous-Runs climatology | Spread-percentile selection limited to ensemble window. |
| **H3** | AI-vs-physics disagreement gate | 🟡 | multi-ensemble (90d) | Kill-test (does D add skill beyond within-ensemble S?) runnable on 90d with weak power. |
| **H6** | Tail exceedance vs round-number | 🟡 | ensemble (90d) + ≥80 resolved tails/station | Round-number *behavioral* half testable from tail-price history + CLI; ensemble-exceedance half window-limited. Catalog flags it a forward-collection project. |
| **H29** | EMOS-calibrated AIFS-ENS | 🟡 signal-only | AIFS ensemble (~90d) + CLI | Calibration on ~90d; EV ❌ until forward-log. |
| **H33** | Pooled super-ensemble | 🟡 | 4 ensembles, AI feeds ~90d | Restricted to overlapping-archive dates (short). |
| **H34** | Skew-aware AI distribution | 🟡 | ensemble members (~90d) | Skew-vs-symmetric Brier on the short window. |
| **H35** | AI prior + floor hand-off | 🟡 | AI prior (90d) + floor (✅) | Floor stage ✅; AI-prior stage 90d-limited. |
| **H37** | NOAA EAGLE commercial-safe feed | 🟡 heavy | **AIWP reforecast on AWS S3 (long archive!)** + CLI | The *only* AI hypothesis with a real multi-year backtest archive — but heavy GRIB2 ingestion (Herbie/S3). Worth it as the production+backtest feed. |
| **H28** | Multi-product μ-divergence | ❌ | **NBM NBP + MOS text — no archive** | Forward-snapshot only. (Interim = use ensemble spread = H1, on 90d.) |
| **H17/H22** | NBP percentile fan | ❌ | **NBM NBP text — no archive** | Forward-collect for weeks before any calibration claim. |
| **H41** | Neglect-by-volume cold-start picker | 🟡 | candlestick volume/OI (✅) + ensemble spread (90d) | Volume/OI neglect prior ✅; variance input 90d. A funnel, not a trade — validate ranking vs H10. |

*(Merged overlays — H2/H8/H15/H16/H19/H21/H23/H24/H25/H26/H30/H36/H40/H43 —
inherit the grade of their parent.)*

---

## Build-and-test-now in the sandbox (the ✅ set)

These need only **archived** data and can be validated before risking a dollar.
They are mostly the settlement-replication / structural / deterministic-bias
family — and they overlap almost exactly with the catalog's own Top-10 and its
"most durable" list:

1. **H11** — LST/DST correctness (deterministic property; also fixes a live `weather.py` bug).
2. **H7** — Running-Max Floor (the ~100%-hit-rate self-test of your settlement code).
3. **H27b** — Post-Peak Lock gap (strongest survivor *and* fully offline-testable).
4. **H10** — Responsiveness screen (the allocation brain; gates everything else).
5. **H14** — Tail monotonicity locks (model-free, price-only).
6. **H20** — Forecast→CLI bias (years of signal history; no ensemble).
7. **H9** — Quantization replicator (validate the rounding chain against CLI).
8. **H42** — Spread-compression rotate-out (venue-internal microstructure).
9. **H38** — Conditional UHI bias (long signal history; watch winter sample size).
10. **H39** — Correlation cap (risk backtest on realized multi-city CLI).

Codex's first job is the **shared infra** these all sit on: the
**settlement-replication module** (running-max, °C→°F lattice, LST window, station
map incl. the CHI=KMDW fix), the **METAR-T-group obs-path reconstructor** (the IEM
1-min substitute), the **bucket-ladder PMF builder** (doesn't exist yet), and the
**no-lookahead backtester over candlesticks** (fees via `round_up(0.07·P·(1−P))`,
fills as top-of-book proxy). Every ✅ above is then a thin strategy on top.

## Can't test offline yet (forward-collection)

- **H28, H17/H22** — NBM/MOS have no archive. Stand up a snapshot collector now so
  the corpus exists in a few weeks; until then, untestable.
- **EV (not signal) for the whole ensemble family (H1/H5/H6/H29/H33/H34/H35)** —
  ~90-day ensemble window + thin candlestick overlap means you can prove the
  *signal calibrates* but not that the *trade pays*. Don't size these on backtest;
  size them after forward-logged EV accrues. (Exception: H37 via AIWP reforecast.)

## Bottom line

The constraint **inverts the naive expectation**: the "sophisticated" ensemble/AI
calibration hypotheses are the *data-starved* ones for backtesting (90-day window,
no archive), while the "boring" settlement-replication, structural-lock, and
deterministic-bias hypotheses are *fully* offline-testable on real archives — and
those are also, per the catalog, the most *durable* edges. So the sandbox-testable
set and the build-first set are nearly the same list. Start there.
