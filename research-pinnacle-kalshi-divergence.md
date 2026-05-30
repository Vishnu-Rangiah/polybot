# Research & Plan — Pinnacle ↔ Kalshi Divergence Strategy

> Scratch/research doc. Goal: trade Kalshi sports contracts that have drifted from
> Pinnacle's de-vigged "fair" price. Pinnacle = sharp anchor, Kalshi = retail venue
> that lags. This is *value betting*, not arbitrage — we don't need both legs, we
> need a better probability estimate than the Kalshi crowd, sourced from Pinnacle.
>
> Status: pre-build research. Nothing here is committed code yet.
> Date: 2026-05-30.
>
> ⚠️ READ SECTION 10 FIRST — viability findings that refine (and partly challenge)
> the thesis. The edge is real but lives in a narrow niche, NOT on flagship games.

---

## 1. The thesis (and why it's sound)

```
edge = (crowd pricing error on Kalshi)  vs  (de-vigged Pinnacle fair value)
```

- **Pinnacle is the industry benchmark for "true probability."** Low margins, high
  limits, welcomes sharp money, lets its line move to the truth. Its closing line is
  widely regarded as the most accurate representation of true probability in the
  industry. So "Pinnacle fair = truth, Kalshi drift = mispricing" is a legitimate
  framework, not wishful thinking.
- **Edge plausibly exists on Kalshi specifically** because Kalshi sports markets are
  newer, thinner, and driven by retail flow that doesn't track sharp movement
  promptly. When news moves Pinnacle, Kalshi can lag — that lag is the window.
- **Sports is huge on Kalshi**: 89% of Kalshi's 2025 fee revenue (~$263.5M total)
  came from sports. Liquidity and contract coverage are there.

This is the *good* version of cross-venue trading: no crypto settlement race, no
nanosecond bots (that was the Kalshi↔Polymarket arb). We exploit an information/speed
gap between a sharp book and a retail venue — slower, more accessible, DSC-shaped.

---

## 2. The core math: de-vigging Pinnacle

Pinnacle's two sides **don't sum to 100%** — they sum to ~102–103% (the vig). We must
remove the vig to get the implied fair probability.

Worked example (multiplicative):
```
Pinnacle: Team A 1.90 / Team B 2.02 (decimal)
raw implied:  1/1.90 = 52.6%    1/2.02 = 49.5%    → sum 102.1% (the overround)
de-vigged:    52.6/102.1 = 51.5%   49.5/102.1 = 48.5%   → sum 100%
```
The **51.5%** is fair value — NOT the raw 52.6%.

### De-vig method choice (a real DSC sub-experiment)
| Method | How it works | When to use |
|---|---|---|
| **Multiplicative** | Spread vig proportionally to implied prob | Default; great for low-vig books like Pinnacle |
| **Additive** | Distribute overround equally | Simplest; weakest |
| **Power** | Raise implied probs to a constant power | Better for lopsided/longshot odds |
| **Shin** | Iterative; models informed bettors, corrects favorite-longshot bias | Academic standard; best predictive accuracy |

**Recommendation:** start with **multiplicative** (Pinnacle's vig is low, ~2–3%, so
method barely matters). Keep **Shin** as a later experiment and compare calibration of
each — that comparison is itself a nice writeup.

Signal:
```
divergence = kalshi_price_yes − pinnacle_devigged_prob_yes   (both in [0,1])
```

---

## 3. Data sourcing — the plan's biggest constraint

**KEY FINDING: Pinnacle shut down its public API on 2025-07-23.** It now serves only
"select high-value bettors & commercial partnerships" (academics can email
api@pinnacle.com). So we cannot hit Pinnacle directly. Options:

| Source | Notes | Rough cost |
|---|---|---|
| **The Odds API** (the-odds-api.com) | Aggregator, includes Pinnacle, has a free tier | Free tier → paid |
| **SportsGameOdds / OpticOdds / SportsFirst** | Commercial Pinnacle feeds | ~$299/mo+ |
| **Historical Pinnacle datasets** (bettingiscool, etc.) | Line-movement history — perfect for the *backtest* | One-time/sub |
| **Pinnacle academic access** | Email api@pinnacle.com; we have a research use case | Free if granted |

**Plan:**
- **Backtest phase:** use a historical Pinnacle line-movement dataset + recorded Kalshi
  snapshots (we already log `outputs/snapshots.jsonl`). No live feed needed to validate
  the edge — this de-risks everything before spending on a feed.
- **Live phase (only if backtest shows edge):** subscribe to an aggregator with Pinnacle
  coverage (start with The Odds API free/cheap tier).
- Check each provider's ToS for automated use.

---

## 4. Cost model — what the edge must clear

### Kalshi fees (confirmed formula)
- **Taker:** `ceil(0.07 × C × P × (1−P))` cents, where C=contracts, P=price in dollars.
  Peaks at **~1.75¢/contract at 50¢** (50/50), shrinks toward the extremes.
- **Maker:** `ceil(0.0175 × C × P × (1−P))` — only some markets; often rebated for MMs.

### Total cost to beat per trade
```
required_edge > taker_fee(P) + spread_crossed + safety_buffer
```
- A divergence near 50/50 must clear ~1.75¢ fee + spread. A 1.5¢ drift is net-negative.
- The existing `strategy.py` already encodes `COST_BUFFER_CENTS = 3` and
  `MIN_EDGE_CENTS = 6` — but those are *flat*. **Upgrade:** make the fee term the real
  P-dependent Kalshi formula, not a flat 3¢ (flat under-charges near 50/50, over-charges
  at the extremes).

---

## 5. The killer validation: CLV (zero money at risk)

We can prove the edge is real **without betting a dollar** by measuring **Closing Line
Value** — the single best-established predictor of long-run betting profit. Pinnacle's
own research: bettors with positive CLV were almost universally profitable over time,
regardless of short-term variance. Over 1,000+ bets, consistent positive CLV is
"mathematically almost impossible to lose."

**Our CLV test:**
1. Log time-synced pairs: `(kalshi_book_t, pinnacle_devigged_fair_t)`.
2. Flag divergences past the fee-aware threshold → "would-bet" events.
3. Measure: did the **Kalshi price subsequently move toward Pinnacle by close**?
   - Positive CLV consistently → real edge.
   - No convergence (or Kalshi was right and Pinnacle moved to it) → thesis dead, $0 lost.
4. Secondary checks:
   - Did flagged divergences predict actual **resolution** profit?
   - Is de-vigged Pinnacle itself **calibrated** vs outcomes? (Should be near-perfect;
     a sanity check on the whole pipeline — Brier score, reliability diagram.)

This is a complete, publishable DSC study with a clean yes/no answer.

---

## 6. Gotchas (go in clear-eyed)

1. **You're not first.** This is the most obvious sports strategy that exists; odds-
   comparison bots and value bettors watch Kalshi-vs-sharp gaps too. Big slow
   divergences get eaten — fish for small/fast ones. Slower than crypto arb, not free.
2. **Stale data ≠ real divergence.** If the Kalshi snapshot is newer than the Pinnacle
   pull, "drift" can be pure timing artifact. **Time-synced snapshots are mandatory** —
   stamp every quote, discard stale pairs. (Repo already stamps `observed_at_ms`; do the
   same for Pinnacle and enforce a max skew.)
3. **Contract matching must be exact.** Kalshi resolution must map precisely to the
   Pinnacle market (moneyline vs spread, OT rules, withdrawal/forfeit handling). A
   resolution-rule mismatch produces *fake* divergence. This is where `rule_parser.py`
   earns its keep.
4. **Fees must clear** (Section 4).
5. **Pinnacle isn't always first.** On fast breaking news (injury scratch), Kalshi or
   another source can briefly lead. The "Pinnacle = truth" assumption is ~95% safe.
6. **Data ToS / cost.** Post-API-shutdown, Pinnacle data costs money or needs academic
   access. Budget for it; don't scrape against ToS.

---

## 7. Architecture — how it drops into the existing repo

The repo is already cleanly factored, and the injection point is *perfect*:
`strategy.py` already consumes `state.features["fair_prob_yes"]`. A Pinnacle-derived
fair probability lands in that dict and the existing edge logic runs unchanged.

| Layer | Existing file | Change needed |
|---|---|---|
| Data in | `datasource.py` | Add a **Pinnacle/odds-API source** alongside Kalshi (same `get_state`-style contract or a parallel fetcher keyed by event) |
| Wire format | `normalize.py` | Add **de-vig** util: decimal/American odds → de-vigged fair prob (multiplicative first) |
| Matching | `rule_parser.py` | Map Kalshi ticker ↔ Pinnacle event/market; reject resolution-rule mismatches |
| Feature join | (new) `pinnacle.py` | Fetch → de-vig → produce `features["fair_prob_yes"]` + `features["pinnacle_observed_at_ms"]` |
| Signal | `strategy.py` | Already works; **upgrade** flat cost buffer → P-dependent Kalshi fee; add max-staleness guard |
| Validation | (new) `clv_backtest.py` + `outputs/` | CLV scorer, calibration (Brier/reliability), edge-vs-resolution PnL |
| Risk/exec | `risk.py`, `executor.py` | Unchanged; ready for live phase |

Data convention note: repo uses **integer cents [0,100]** for money and floats for
`*_prob`. De-vig produces a prob → convert to cents only at the edge comparison, matching
the existing pattern in `strategy.py:decide`.

---

## 8. Build plan (phased, de-risked)

**Phase 0 — De-vig core (pure, testable, no network)**
- `devig(odds, method="multiplicative") -> fair_probs`. Unit-test against the worked
  example. Add `american_to_decimal` / `decimal_to_prob` helpers.

**Phase 1 — Matching**
- Map a handful of Kalshi sports tickers to their Pinnacle events. Hand-verify resolution
  rules align. Start with one league (clean moneylines, e.g. a major team sport).

**Phase 2 — Offline backtest (the heart; zero money, zero live feed)**
- Use a historical Pinnacle dataset + recorded Kalshi snapshots.
- Compute divergence series; flag fee-aware "would-bet" events.
- **CLV scorer:** did Kalshi converge toward Pinnacle by close?
- **Calibration:** Brier score + reliability diagram for de-vigged Pinnacle vs outcomes.
- **Decision gate:** only proceed if CLV is consistently positive after fees.

**Phase 3 — Live paper trading**
- Add aggregator feed (The Odds API tier w/ Pinnacle).
- Time-synced Kalshi + Pinnacle snapshots, max-skew guard.
- Run `strategy.decide` with real `fair_prob_yes`; route to the **paper** executor.
- Track live CLV + paper PnL; compare to backtest.

**Phase 4 — (optional) tiny real money**
- Only if paper CLV holds. Size with fractional Kelly. `risk.py` enforces caps.
- Treat as tuition, not income.

**Stretch / DSC experiments**
- Compare de-vig methods (multiplicative vs Shin) by calibration.
- Model the *lag*: how long does Kalshi take to converge? Does divergence half-life
  predict CLV? (A nice time-series sub-study.)
- Per-league edge breakdown (where is Kalshi laggiest?).

---

## 9. Decision gate (be honest with yourself)

The whole project hinges on Phase 2. **If backtested CLV after fees isn't consistently
positive, the edge isn't there — stop, write it up as a negative result (still a great
DSC portfolio piece), and don't risk money.** Letting the measured CLV decide — not the
"where's the retail" intuition — is the data-science way.

---

## 10. Viability update — where the edge actually lives (key findings)

Fresh research both **validates the method** and **squeezes the opportunity**. Read this
before building — it changes *which markets* to target.

### The strategy is real and documented
A value-betting source describes our exact approach verbatim: *"the gap between the
devigged Pinnacle number and the Kalshi price is your value bet edge... bet when Kalshi
is offering at least 2–3% of edge."* So we're not inventing something; the playbook
exists. Good (idea is sound) and sobering (others run it already).

### BUT — the original "Pinnacle sharp, Kalshi laggard" framing is only half true
The big surprise: **Kalshi's overround is ~100.0–100.5%, vs Pinnacle's ~102%** and
retail books' 105–108%. On liquid games, *"the difference shows up as better implied
prices than even sharp sportsbooks like Pinnacle."*

**Implication:** on flagship liquid games (NBA/NFL/MLB primetime), Kalshi is often **as
sharp as or sharper than Pinnacle**. There, "Pinnacle = truth, Kalshi = lag" does NOT
hold — if anything Kalshi *is* the sharp price. The naive divergence signal will mostly
fire on noise/timing there, and arbitrage "is rarely large enough on flagship markets to
be worth it in isolation."

Concrete scale of typical gaps — Chiefs–Bills (May 2026): Kalshi KC 58.5% vs DraftKings
devigged ~57.4% → ~1.1% gap, *below* the 2–3% threshold. Gaps are usually small.

### The liquidity squeeze (the real constraint)
- **Liquid games:** spreads 1–3¢, Kalshi ≈ or sharper than Pinnacle → **little edge**.
- **Illiquid games:** spreads **5–10¢ wide** → *"eats up your edge fast."* The divergence
  exists but the spread you cross to capture it is bigger than the edge.

So the edge is pinched from both sides: efficient where it's liquid, spread-eaten where
it's not.

### Where that leaves a real, reachable edge (the niche to target)
1. **Transient lag on otherwise-liquid games** — the moment sharp news moves Pinnacle and
   Kalshi hasn't caught up yet. Liquid enough for tight spreads, briefly mispriced.
   *This is a latency-tolerant-but-not-slow window — measure how long it lasts.*
2. **The liquidity "sweet spot"** — games liquid enough for ~1–3¢ spreads but not so
   flagship they're perfectly efficient (secondary games, non-primetime, less-covered
   leagues). Enough volume to fill, enough inefficiency to matter.
3. **Cumulative small edge at scale**, not one big hit — the sources stress the value is
   *"the cumulative pricing advantage on volume,"* not isolated home runs. Many small
   +2–3% edges, sized with discipline.
4. **Account/size limits cut both ways:** sportsbooks limit +EV bettors, but Kalshi
   liquidity caps your size — so this stays small-scale, which fits a side project fine.

### Revised verdict
- **Method: validated.** De-vig Pinnacle, compare to Kalshi, bet the gap — this is a
  documented real strategy.
- **Easy/flagship edge: gone or never existed** — Kalshi is too sharp there.
- **Reachable edge: narrow** — transient lag + the liquidity sweet spot, captured as many
  small +2–3% (post-fee) edges. The CLV backtest (Section 5) must now specifically test:
  *does the edge survive after fees AND the spread crossed, in the non-flagship band?*
- **As a DSC project: more interesting, not less.** "Where exactly does Kalshi stop being
  efficient?" is a sharper, more publishable research question than "can I beat the
  market." Even a clean negative result maps the efficiency frontier.

### Backtest design changes this forces
- Segment everything by **liquidity tier** (spread width / volume) — the edge is a
  function of tier, so a blended number will hide it.
- Subtract the **spread actually crossed**, not just fees — on illiquid games the spread
  is the dominant cost.
- Add a **lag/half-life study**: when Pinnacle moves, how long until Kalshi converges?
  That half-life *is* the tradeable window and a great time-series sub-analysis.

---

## 11. Behavioral bias — the targeting layer (academically documented on Kalshi)

This answers "are there *specific* games where Kalshi is less efficient?" — **yes, and the
biases are quantified in peer-grade research on 292M+ trades / 327k contracts.** This is
the most important strategic finding: it turns "hunt random divergence" into "hunt
divergence *in the direction Kalshi is known to systematically err*." The Pinnacle de-vig
gives fair value; these biases give a **prior on which way Kalshi will be wrong**, so you
know where to point the search and which side to lean.

### Documented, exploitable biases on Kalshi specifically
1. **Favorite–longshot bias (confirmed on Kalshi, quantified).** Low-price (longshot)
   contracts win *far less* than break-even after fees; high-price (favorite) contracts
   win *more* and yield small positive returns. → Longshots systematically OVERpriced,
   favorites UNDERpriced. Lean: buy underpriced favorites, fade overpriced longshots.
2. **YES-overbet / positive-outcome herding.** Traders systematically overbet YES in
   markets that predominantly settle NO — sentiment-driven herding toward the "exciting"
   side. → The YES contract on a hyped/underdog narrative is often too expensive.
3. **"Underdog bias."** Longshot prices made *more expensive than fair value* — the same
   error a second source confirms. Reinforces #1.
4. **Compression toward 50% at long horizons (underconfidence).** Far from resolution,
   prices are too compressed — favorites underpriced. Strongest in politics but
   generalizes. → Edge is bigger *earlier*, before the crowd sharpens near game time.
5. **Takers lose ~32% on average; makers lose ~10%**, and the favorite-longshot pattern
   is *much stronger for takers.* → HUGE practical implication: **post limit orders (be a
   maker), don't cross the spread (taker).** Being a maker roughly halves the structural
   bleed AND the bias works less against you. This also directly attacks the Section 10
   "spread eats your edge" problem — a maker *earns* the spread instead of paying it.

### Mapping to your hypotheses (you were right)
- **"High bias" games →** favorite-longshot + underdog + YES-herding all concentrate on
  games with a popular *narrative* underdog or a hyped storyline. Those are exactly where
  Kalshi longshots get overpriced.
- **"Lots of retail from aggressive ads" →** heavily-marketed events pull disproportionate
  *uninformed* flow → more bias. Kalshi's social feed (sentiment posts, herding — visible
  in-app) plausibly amplifies positive-outcome herding (#2). The flip side (Section 10
  tension): the *most*-advertised events are also the most liquid, so they attract the
  most sharp correction. Net edge depends on whether sharp capital is
  capacity-constrained on that event — an empirical question for the backtest.
- **Caveat — Kalshi is a CLOB, NOT a gamified AMM** with staking tiers (that's some crypto
  venues). So "gamification" isn't the mechanism; the mechanism is a social feed + heavy
  retail takers on a real order book. Bias is real, the framing should be precise.

### Public-team distortion (from the broader sports-betting literature)
Popular franchises (Cowboys, Lakers, Man U) draw heavy public money → "public favorite
distortion." On a sportsbook the *book shades the line* to balance liability; on Kalshi's
CLOB there's no book setting a line, so retail flow itself moves price and only sharp
arbs correct it. → When a popular team is heavily publicly backed, its Kalshi price can be
bid above fair. (This can *offset* the favorite-longshot underpricing — which is exactly
why you anchor on **de-vigged Pinnacle as ground truth** and let the measurement, not the
theory, decide. The biases tell you where to *look*, Pinnacle tells you the *answer*.)

### How this upgrades the strategy
The signal is no longer just `kalshi − pinnacle_fair`. It's that **plus a bias prior**:
- Prioritize trades where divergence *aligns* with a documented bias (buying favorites
  Kalshi underprices; fading longshots/hyped-underdog YES it overprices). Higher
  confidence, higher hit rate.
- **Default to maker (limit) orders** — earn the spread, dodge the taker bleed.
- Hunt **earlier in the market's life** (compression bias bigger before game time).
- Segment backtest by: favorite/longshot, YES/NO settle, marketing intensity (proxy:
  volume spike / trending), time-to-resolution, popular-team flag. The bias structure
  *is* the feature set.

### The rigorous sources to actually read (this is your DSC lit review)
- **Bürgi, Deng & Whelan — "Makers and Takers: The Economics of the Kalshi Prediction
  Market"** — the taker −32% / maker −10% and favorite-longshot results.
- **Le (2026) — "Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in
  Prediction Markets"** (arXiv 2602.19520) — 292M trades, calibration by domain/horizon.
- **Bartlett & O'Hara — "Adverse Selection in Prediction Markets: Evidence from Kalshi"**
  (SSRN) — adverse selection / who-loses-to-whom.
- **QuantPedia — "Systematic Edges in Prediction Markets"** — practitioner summary.
- **github.com/spfunctions/prediction-markets-reading** — 256-article reading list.

### Verdict refinement
Section 10 said the edge is narrow. Section 11 says it's narrow **but structured and
predictable** — which is far more tradeable than narrow-and-random. The combination of
(a) de-vigged Pinnacle fair value, (b) documented directional bias, and (c) maker-side
execution is a genuinely coherent edge thesis. The backtest now has clear features to
test, and the lit above gives you effect sizes to compare your results against.

---

## 12. Player props — the steep, durable efficiency gradient (likely the best thesis)

The insight: props aren't liquid yet on prediction markets, but are huge on
sportsbooks/DFS. So use the mature props market as fair value, trade the nascent Kalshi
version that hasn't caught up. **This is arguably the strongest thesis in this doc** —
it stacks three documented edges — but it carries a new, serious risk (integrity/adverse
selection). Details below.

### Current state (verified)
- **Kalshi ALREADY launched NBA player props** (points, rebounds, assists, 3-pointers)
  and **NFL props** — but coverage is **thin: ~5 players max per game.** So it's both
  "live now" *and* "early-market." That's the sweet spot.
- This stacks: (a) **new-contract-launch edge** (Section 11 #4 — before algos calibrate),
  (b) **cross-venue lag** (Kalshi props lag the deep sportsbook props market), (c) **you
  can be the maker** in a thin book and provide liquidity at favorable prices.

### CRITICAL correction: the props consensus is LIQUID but NOT sharp
Do not treat FanDuel/PrizePicks props as "truth" the way Pinnacle game lines are:
- **Props are the *softest*, most-exploitable area of sports betting** — lower limits,
  less sharp attention, **heavier juice (-115/-120+, ~8%+ hold per side** vs ~4.5% on
  game lines). Soft *everywhere*, not just on Kalshi.
- **PrizePicks is pick'em (DFS), not two-way odds** — there's no line to de-vig; its
  "line" is a projection embedding a large house edge. Use it only as a cross-check, NOT
  as the fair-value anchor.
- **Correct fair value = de-vigged CONSENSUS across multiple sportsbooks' two-way prop
  odds** (FanDuel + DraftKings + Pinnacle/Circa where they post props). FanDuel is cited
  as the single most important source; Pinnacle/Circa are the sharp filters. Consensus
  beats any single soft book.

### Why an edge still exists despite props being soft everywhere
It's the **gradient**, not absolute sharpness. A deep multi-book props consensus (even at
8% hold) is a *far* better probability estimate than a brand-new Kalshi prop with five
players and a handful of traders. The Kalshi version is *softer and laggier than the
already-soft consensus* — that difference is the edge. Steeper and more durable than the
game-moneyline gradient (Section 10), where Kalshi was already as sharp as Pinnacle.

### NEW RISK — integrity / adverse selection (take seriously)
- Kalshi added props **"in the wake of scandals involving player prop betting in the NBA
  and MLB,"** with "protections in place." Player props are *the* locus of insider/
  integrity problems — a player resting, a hidden injury, or manipulation.
- **As a maker on a thin prop book, you are maximally exposed to informed flow.** This is
  the Bartlett/O'Hara *adverse selection* result made concrete: someone who knows the
  star is sitting picks off your resting limit order. On a 5-player thin market, one
  informed taker can be most of your counterparties.
- Mitigations: tiny size; monitor injury/lineup news up to tip; avoid resting maker
  orders right before lineup locks; widen quotes around uncertain players; consider
  taker-only when you have a *specific* consensus-divergence signal rather than passively
  making.

### Extra matching difficulty for props
Resolution mapping is harder than game lines: stat definitions (does Kalshi "points"
include OT?), push/exact-line handling, and Kalshi's contract structure (over/under X.5
vs discrete buckets) must align *exactly* with the book line you're comparing. A
half-point or OT-rule mismatch creates fake edge. `rule_parser.py` work is heavier here.

### Verdict
Best risk/reward thesis in the doc *if and only if* the integrity/adverse-selection risk
is respected. Plan: build de-vigged multi-book props consensus → compare to thin Kalshi
props → CLV-backtest by player/stat → start taker-only on clear divergences, graduate to
small maker quotes only where adverse-selection risk is low (low-injury-variance roles).

---

## 13. Live / in-game overreaction — best DSC fit, different anchor problem

The play: pregame lines are sharp (set by advanced books). But **during** the game,
retail swoops in to live-bet and overreacts to what just happened, pushing the live
price off fair value. You fade the overreaction. **Academically supported and the best
fit for a data-science project — but the fair-value anchor is now a MODEL you build, not
a book you copy, which is both the opportunity and the risk.**

### Why it's real (documented)
- **Recency/overreaction bias is strongest live.** Krieger, Davis & Strode (NFL market)
  and in-game-betting studies: bettors are "erroneously influenced by recent performance,
  creating profitable opportunities for those less subject to recency bias." Pregame
  (sharp-set) lines resist this; live markets, driven by retail, overreact.
- **Most "momentum" is variance.** A team shooting 42% from three over five games is
  usually positive variance regressing to mean — retail treats it as a permanent shift
  and the price overshoots. That overshoot is the edge.
- **The mechanism:** favorite gives up an early goal → public panics → hammers the
  underdog → price moves *further than true probability warrants* → you fade it.
- **Kalshi supports it:** "unmatched market activity for live sports trading" across many
  sports, highly liquid. The opening-screenshot tennis market (live ticking price + "ITALYYYY"
  sentiment posts) is exactly this environment.

### THE KEY DIFFERENCE: your anchor is a live win-probability model
Pregame Pinnacle is stale the instant tip-off happens. So fair value during the game must
come from a **live win-probability (WP) model**: game state (score, time, possession,
etc.) → P(win), updating continuously. This is described as *the* prediction-market live
tool: "WP model says 72%, Kalshi trades 65¢ → 7-point edge."

**This is why it's the best DSC fit:** the edge lives in a **model you build**, not a data
feed you buy (pregame play needs Pinnacle; props play needs a paid consensus odds feed).
The WP model is the product, the moat, and a pure data-science artifact — and it drops
**straight into the existing architecture**: WP model → `features["fair_prob_yes"]` →
`strategy.decide` compares to the Kalshi ask, unchanged.

### The double-edged sword (the risk this introduces)
Because the anchor is *your* model, **your edge is only as good as your model's
calibration.** If your WP model is worse than the Kalshi crowd's implied probability, you
have *negative* edge and won't feel it until you've lost money. So:
- **Calibration is paramount.** The WP model must be proven (a) calibrated vs outcomes
  (Brier/reliability) AND (b) *sharper than the live Kalshi price* (encompassing
  regression, Section "choosing fair value"). Public sports WP models are strong
  benchmarks to validate against — don't ship a homemade model you haven't beaten them with.
- **Distinguish real state-changes from variance.** Sometimes "momentum" is real (key
  injury, pitcher gassed, red card). The model must incorporate genuine state changes, not
  blindly mean-revert. That discrimination is the core modeling challenge.

### Latency returns — moderate, not HFT
Unlike pregame/props (slow), live is latency-sensitive: game-state → WP recompute →
compare → act, before Kalshi corrects. But you're racing **retail emotional lag**, not
FPGA bots, so windows are plausibly seconds-to-tens-of-seconds → reachable with a
cloud-region VPS + fast feed (Tier 1–2 from the latency ladder), NOT colo/FPGA. Caveats:
- **Broadcast vs feed delay is the silent killer.** The Kalshi crowd reacts to the TV
  broadcast. If your play-by-play feed lags the broadcast, the crowd is *ahead* of you and
  you're trading stale model output. Sharp in-game bettors obsess over getting game state
  *faster* than broadcast. Measure your feed-vs-broadcast delay explicitly.
- **In-game algos exist** and are growing — you're not alone. Bet that Kalshi's retail,
  social-driven overreaction persists *longer* than on a sharp live book.

### New data dependency: a live play-by-play feed
The linchpin. Options: official/league feeds (Sportradar/Genius — expensive), ESPN/
scoreboard scraping (cheap, ToS + latency risk), or Kalshi's own data. Feed latency
directly bounds the edge. For a side project, start with a cheap/scraped feed on ONE
sport and measure feed-vs-broadcast delay before trusting any signal.

### CLV still works (live variant)
Measure whether your model-flagged live entries beat the *subsequent* live-market price
(did Kalshi move toward your WP estimate after you'd have traded?). Same zero-money
validation, applied to live ticks.

---

## 14. Thesis comparison — ranking the four plays

| Play | Edge size | Durability | DSC fit | Latency need | Data cost | Main risk |
|---|---|---|---|---|---|---|
| **Game moneylines** (pregame, vs Pinnacle) | Low — Kalshi ≈/sharper than Pinnacle | Low | Low | Low | Med (sharp odds) | No edge on flagships |
| **Pregame player props** (vs book consensus) | High (steep gradient) | Med (gap closes as props mature) | Med | Low | High (multi-book props feed) | Integrity / adverse selection |
| **Live / in-game overreaction** (vs WP model) | High (documented) | High (recency bias is permanent) | **Highest** (you build the model) | Med (cloud+fast feed) | Med (play-by-play feed) | Your model must beat the crowd; feed-vs-broadcast lag |
| **Bias-tilted divergence** (Section 11 overlay) | Adds to any of the above | — | High | — | — | Overfitting to past bias |

**Read:** game moneylines are the weakest (efficient). Props have the steepest gradient
but cost (data) and integrity risk. **Live/in-game is the best DSC project** — the edge is
documented, durable (recency bias never goes away), and lives in a model you build that
slots into the existing code — at the cost of moderate latency engineering and the burden
of proving your model beats the crowd. A natural progression: **prove a calibrated WP
model offline first (cheap, no risk), then live-paper-trade it vs Kalshi.**

---

## 15. The meta-edge — infrastructure / data / tooling ("picks & shovels")

Realization after mapping all four trading theses: **the biggest, most durable edge may
not be trading at all — it's building the data/API/tooling layer the traders need.**
Classic gold-rush logic: shovel-sellers capture value with far less variance than miners.

### This research is its own evidence
*Every* trading thesis bottlenecked on infrastructure, and each bottleneck is a business:
- **Pregame play** → Pinnacle shut its API (2025); vendors now charge **$299/mo+** for
  sharp odds (Section 3). That vendor *is* the shovel business.
- **Props play** → needs a paid multi-book **consensus odds feed** (Section 12).
- **Live play** → needs a fast **play-by-play feed**; feed-vs-broadcast latency is the
  whole game (Section 13).
- Aggregators (the-odds-api, OddsJam, OpticOdds, Unabated) thrive selling exactly this.
- The recurring demand signal: a clean **"Kalshi/Polymarket API in Python" guide** keeps
  showing up — i.e., people want PM data tooling that barely exists yet.

### Why it fits a solo DSC side project *better* than trading
- **Non-adversarial.** Trading is zero-sum vs sharps and bias; tooling isn't — you're not
  trying to beat anyone, just be useful.
- **Durable artifact, not just PnL.** You end with a library / dataset / dashboard — a
  portfolio piece that compounds, vs a P&L line that resets.
- **Sidesteps the hardest problem** ("must beat the crowd / sharps").
- **Same skillset** — APIs, data engineering, modeling, calibration — all DSC.
- **Already half-built.** `kalshi_agent` IS infrastructure: the normalized `MarketState`
  abstraction, the (planned) devig library, the WP model, the CLV/calibration backtester
  are reusable components, not throwaway strategy code.

### Accessibility ladder (honest)
- ❌ **Build an exchange/venue** ("build the market" literally) — capital + CFTC
  regulation; not solo-realistic.
- 🟡 **Market making** — the Section 11 maker edge is real (makers −10% vs takers −32%),
  but needs capital and competes with SIG-class MMs. Possible at tiny scale, not a moat.
- ✅ **PM-native data / analytics / tooling** — the accessible, durable one. It's *younger*
  than sportsbook tooling, and you have a head start. Specific gaps worth building:
  - A clean **Python SDK** for normalized Kalshi/Polymarket order books (the `MarketState`
    layer, generalized + open-sourced).
  - A **de-vig / fair-value library** (multiplicative/Shin) — reusable, currently scattered
    across paywalled calculators.
  - **Cross-venue fair-value + divergence engine** (Kalshi vs Polymarket vs book consensus).
  - **CLV + calibration analytics for prediction markets** — turn the Section 11 bias work
    into a dashboard/dataset. Nobody's really productized PM-specific calibration.
  - **WP-model-as-a-feed** for live markets.

### Honest caveats
- The tooling space has **incumbents**; "build an API" generically isn't an edge. The edge
  is a *specific gap* + being **PM-native** (most tools are sportsbook-native) + your
  existing head start.
- **Building useful ≠ monetizable.** A great open-source SDK builds reputation/portfolio;
  turning it into revenue is a separate problem (support, data licensing, ToS).
- **Data ToS/licensing** is the recurring legal constraint for any data product.

### Verdict / how to have it both ways
For a *fun DSC side project that compounds into something durable*, the infrastructure
framing likely beats the pure-trading framing. And you don't have to choose: **build the
tooling, then use it to trade small.** The library/dashboard/dataset is valuable whether
or not the trading edge ever materializes — which de-risks the whole endeavor. The build
order barely changes: the same `devig`, normalization, WP-model, and CLV components are
Phase 0 *either way* — you're just deciding whether the end product is "a bot" or "a
toolkit (that happens to power a bot)." Recommend: **build them as a clean, documented,
open-sourceable toolkit from day one.**

---

## Sources

- Pinnacle API shutdown (July 2025) — https://odds-api.io/blog/pinnacle-api-shutdown-alternatives
- The Odds API — https://the-odds-api.com/
- SportsGameOdds Pinnacle feed — https://sportsgameodds.com/bookmakers/pinnacle-odds-api
- Historical Pinnacle data — https://api.bettingiscool.com/
- De-vig methods explained — https://betherosports.com/blog/devigging-methods-explained
- Shin / no-vig odds — https://betherosports.com/blog/no-vig-odds-explained
- Kalshi fees (help center) — https://help.kalshi.com/trading/fees
- Kalshi fee schedule PDF — https://kalshi.com/docs/kalshi-fee-schedule.pdf
- Kalshi 2025 fee revenue 89% sports — https://finance.yahoo.com/news/kalshi-fee-revenue-2025-263-145801350.html
- CLV explained (Pinnacle) — https://www.pinnacle.com/betting-resources/en/educational/what-is-closing-line-value-clv-in-sports-betting
- CLV as profit predictor — https://oddsjam.com/betting-education/closing-line-value
- Kalshi vs sportsbooks, 4.5% vig gap — https://tech-insider.org/prediction-markets/prediction-markets-vs-sportsbooks/
- Kalshi sports liquidity & spreads — https://tech-insider.org/sports-prediction-markets/
- Devig-Pinnacle-vs-Kalshi value betting + liquidity caveat — https://xclsvmedia.com/kalshi-vs-sportsbooks-2026-can-prediction-markets-replace-your-sportsbook/
- Prediction market efficiency / mispricing — https://www.sports-ai.dev/blog/prediction-markets-vs-bookmakers-ai-betting-2026
- Makers and Takers: Economics of Kalshi (Bürgi/Deng/Whelan) — https://www.karlwhelan.com/Papers/Kalshi.pdf
- Decomposing Crowd Wisdom: calibration dynamics (Le 2026) — https://arxiv.org/pdf/2602.19520
- Adverse Selection in Prediction Markets: Kalshi (Bartlett/O'Hara) — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6615739
- Systematic Edges in Prediction Markets — https://quantpedia.com/systematic-edges-in-prediction-markets/
- Prediction markets reading list (256 articles) — https://github.com/spfunctions/prediction-markets-reading
- Favorite-longshot bias overview — https://www.boydsbets.com/favorite-longshot-bias/
- Cognitive biases / favorite-team bias — https://culture.org/gambling/cognitive-biases-in-sports-betting/
- Public betting percentages / fading the public — https://xclsvmedia.com/public-betting-percentages-explained-how-to-use-2026/
- Kalshi adds NBA prop markets (thin, ~5 players/game) — https://frontofficesports.com/kalshi-adds-nba-prop-markets-as-betting-crackdowns-surge/
- Kalshi launches NBA player props (Gouker) — https://nexteventhorizon.substack.com/p/kalshi-launches-nba-player-props
- Player prop inefficiency / soft lines — https://www.oddsshopper.com/articles/betting-101/sports-betting-prop-strategy-finding-player-prop-inefficiencies-y10
- PrizePicks vs sportsbook props line-shopping — https://oddsjam.com/betting-education/prizepicks-nba-how-to-win-on-prizepicks-with-sharp-player-props
- Recency bias in trading & sports betting — https://www.evidenceinvestor.com/post/new-evidence-on-recency-bias-in-trading-and-sports-betting-1
- NFL gambling: overreaction to news & recency bias (Krieger/Davis/Strode) — https://www.sciencedirect.com/science/article/abs/pii/S2214635021000666
- Bettors' reaction to match dynamics — in-game betting (arXiv) — https://arxiv.org/pdf/2202.10085
- Spotting overreactions in betting markets — https://www.gamblingsite.com/blog/how-to-spot-overreactions-in-betting/
- How win probability models work — https://www.eventedgehq.com/blog/win-probability-models
