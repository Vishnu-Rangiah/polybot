Below are strategy examples ranked from **simple → complex**. Treat these as **research/backtesting ideas**, not trade recommendations.

## 1. Base-rate strategy

**Idea:** Trade when the market price is far from historical frequency.

Example:

```text
Market: Will it rain in NYC today?
Market YES price: 35%
Historical + forecast model probability: 48%
Possible edge: YES looks underpriced
```

Good for:

```text
- Weather
- Sports props
- Election turnout
- Economic release ranges
```

System logic:

```python
if model_probability - market_price > threshold:
    flag_trade()
```

Why it makes sense: prediction markets often overreact to narratives, while base rates are boring but strong.

Main risk: historical base rate may not apply to the current situation.

---

## 2. Weather forecast mispricing

**Idea:** Use structured weather data to price weather markets better than casual traders.

Example:

```text
Market: Highest temperature in San Francisco today?
Market bucket: 67–68°F
Market price: 22%
Weather model probability: 32%
```

Inputs:

```text
- NWS forecast
- Hourly station observations
- Historical same-day distribution
- Time remaining in day
- Station-specific data
```

Best markets:

```text
- Rain today
- High temperature
- Snowfall
- Hurricane landfall
```

Why it makes sense: weather markets resolve objectively and have lots of public data.

Main risk: resolution may use a specific station, not the general city forecast.

---

## 3. Resolution-rule arbitrage

**Idea:** Find markets where people misunderstand the exact resolution criteria.

Example:

```text
Market: Will CPI be above 0.4%?
Important detail: Is 0.4 exactly a YES or NO?
Important detail: Is CPI rounded before comparison?
```

The system looks for:

```text
- Ambiguous wording
- Strict > vs >=
- Initial release vs revised data
- Official source mismatch
- Timezone/date mismatch
```

Why it makes sense: many traders trade the headline, not the actual contract rule.

Main risk: ambiguous markets can resolve unpredictably.

---

## 4. Stale news repricing

**Idea:** Detect public information before the market fully incorporates it.

Example:

```text
Market: Will a bill pass by Friday?
New public update: committee vote scheduled, sponsor says vote delayed
Market still priced as if vote is likely
```

Inputs:

```text
- News
- Official government pages
- Company announcements
- Sports injury reports
- Economic data releases
- Weather advisories
```

System output:

```json
{
  "new_public_information": "Vote delayed until next week",
  "market_implication": "YES probability should fall",
  "current_yes_price": 0.62,
  "model_probability": 0.38,
  "decision": "paper_buy_no"
}
```

Why it makes sense: markets can be slow when liquidity is thin.

Main risk: latency matters, and the public information may already be priced in.

---

## 5. Consensus comparison strategy

**Idea:** Compare Kalshi/Polymarket prices to external consensus probabilities.

Example:

```text
Market: Fed rate cut in June
Kalshi implied probability: 42%
Fed funds futures implied probability: 55%
Difference: 13 percentage points
```

Useful reference markets:

```text
- Fed funds futures
- Sportsbook odds
- Election forecast models
- Analyst consensus
- Crypto options/futures
```

Why it makes sense: prediction markets may lag deeper markets.

Main risk: the two markets may not define the event the same way.

---

## 6. Cross-market consistency strategy

**Idea:** Find logically related markets with inconsistent prices.

Example:

```text
Market A: Candidate wins California = 85%
Market B: Candidate wins election = 30%
Market C: Candidate wins popular vote = 55%
```

Another example:

```text
Market A: BTC above $100k by Dec 31 = 60%
Market B: BTC above $150k by Dec 31 = 55%
```

That second case is impossible because:

```text
P(BTC > 150k) cannot be greater than P(BTC > 100k)
```

The system searches for violations like:

```text
- Nested event inconsistency
- Mutually exclusive outcomes summing above 100%
- Exhaustive outcomes summing below/above fair range
- Related date markets priced inconsistently
```

Why it makes sense: multi-market pricing can become inconsistent.

Main risk: fees, spreads, and liquidity can erase the arbitrage.

---

## 7. Time-decay strategy

**Idea:** As a deadline approaches, uncertainty should shrink. Some markets do not decay correctly.

Example:

```text
Market: Will it rain in NYC today?
At 8 AM: uncertainty high
At 5 PM: no rain yet, radar clear
Market still prices YES at 25%
Model says YES is 8%
```

Good for:

```text
- Weather markets
- Same-day sports markets
- Political deadline markets
- Earnings/event markets
```

Why it makes sense: markets often under-adjust as time runs out.

Main risk: late surprises can still happen.

---

## 8. Event calendar strategy

**Idea:** Trade around known public release schedules.

Example markets:

```text
- CPI
- Jobs report
- Fed decision
- GDP
- Court decisions
- Earnings-related markets
```

System logic:

```text
Before event:
  Build forecast distribution.

At event release:
  Parse official number instantly.

After event:
  Compare final outcome to still-open market prices.
```

Example:

```text
Market: CPI above 0.4%
BLS release comes out: 0.5%
If market still has YES below 95%, there may be a short-lived opportunity.
```

Why it makes sense: objective releases can create very clear resolution signals.

Main risk: competition is high; latency matters.

---

## 9. Order-book imbalance strategy

**Idea:** Use market microstructure to predict short-term price moves.

Inputs:

```text
- Best YES bid
- Best YES ask
- Spread
- Depth at each price level
- Recent trades
- Canceled orders
- Aggressive buy/sell pressure
```

Example:

```json
{
  "yes_bid": 0.41,
  "yes_ask": 0.44,
  "bid_depth": 12000,
  "ask_depth": 2000,
  "recent_trades": "mostly aggressive YES buys",
  "signal": "short-term upward pressure"
}
```

Why it makes sense: order books can reveal demand before price moves.

Main risk: spoofing, thin liquidity, and false signals.

---

## 10. Market-making strategy

**Idea:** Quote both YES and NO sides and earn the spread.

Example:

```text
Fair value estimate: 50%
Quote YES bid: 48%
Quote YES ask: 52%
Earn spread if both sides fill over time
```

Useful when:

```text
- You have strong fair-value estimate
- Spread is wide
- Liquidity is low
- You can manage inventory
```

Why it makes sense: you are paid for providing liquidity.

Main risk: adverse selection. Better-informed traders hit your bad quotes.

---

## 11. Portfolio hedging strategy

**Idea:** Combine related markets to reduce risk.

Example:

```text
Trade 1: YES on CPI > 0.4%
Trade 2: YES on Fed hold
Trade 3: NO on rate cut
```

These are related. A good system should understand that all three may be exposed to the same macro theme.

The agent tracks:

```text
- Correlated exposure
- Maximum loss
- Scenario outcomes
- Portfolio-level drawdown
```

Why it makes sense: individual trades may look good, but the portfolio may be overexposed.

Main risk: correlation can spike during major events.

---

## 12. Bayesian update strategy

**Idea:** Start with a prior probability and update as evidence arrives.

Example:

```text
Prior: 30% chance bill passes this month
Evidence 1: committee vote scheduled → update to 45%
Evidence 2: speaker says floor vote delayed → update to 25%
Evidence 3: official calendar confirms delay → update to 12%
```

This is useful for:

```text
- Politics
- Regulatory approvals
- Legal/court decisions
- Corporate events
- Fed decisions
```

Why it makes sense: many real-world markets are sequential information problems.

Main risk: LLMs can over-update from weak evidence.

---

## 13. Multi-source research ensemble

**Idea:** Combine several independent probability models.

Example for a CPI market:

```text
Model 1: Historical base rate → 46%
Model 2: Component nowcast → 58%
Model 3: Economist consensus → 52%
Model 4: Market-implied prior → 49%

Final ensemble probability → 53%
```

System output:

```json
{
  "ensemble_probability": 0.53,
  "market_price": 0.44,
  "edge_before_costs": 0.09,
  "confidence": "medium",
  "decision": "paper_trade_yes"
}
```

Why it makes sense: no single model is reliable across all market types.

Main risk: models may not be truly independent.

---

## 14. Cross-venue arbitrage

**Idea:** Compare equivalent markets across Kalshi, Polymarket, sportsbooks, futures, or options.

Example:

```text
Kalshi: Event priced at 42%
Polymarket: Same event priced at 51%
Difference: 9 percentage points
```

The system checks:

```text
- Are the markets truly equivalent?
- Are resolution sources the same?
- Are fees different?
- Can both sides be traded?
- Is liquidity sufficient?
```

Why it makes sense: fragmented markets can disagree.

Main risk: “same-looking” markets often have different rules.

---

## 15. Fully autonomous research-to-execution system

**Idea:** The agent scans all markets, researches them, prices them, backtests similar markets, sizes trades, and submits limit orders.

Architecture:

```text
Market scanner
  → Rule parser
  → Evidence retriever
  → Probability model
  → Backtester
  → Risk critic
  → Paper trader
  → Human approval
  → Execution engine
```

This is the most complex version.

The system should only execute if:

```text
- Edge is large
- Liquidity is sufficient
- Resolution rule is clear
- Data is public
- Backtest is positive
- Portfolio risk is acceptable
- Trade passes risk/compliance checks
```

Why it makes sense: this is the full autoresearch-agent vision.

Main risk: too many failure modes. The agent can be wrong about rules, data freshness, probabilities, or execution.

---

## Best order to build

```text
1. Weather base-rate strategy
2. Weather nowcast strategy
3. Resolution-rule parser
4. Economic release nowcast
5. Event-calendar strategy
6. Cross-market consistency checker
7. Stale-news repricing
8. Order-book imbalance
9. Market making
10. Cross-venue arbitrage
11. Portfolio risk engine
12. Fully autonomous agent
```

For a strong first version, build this:

```text
Kalshi Weather Research Agent

Input:
  Kalshi weather market ticker

Output:
  - Resolution rule
  - Current market price
  - Weather forecast probability
  - Historical base rate
  - Fair probability
  - Edge after fees/spread
  - Paper-trade decision
```

That is simple enough to build, objective enough to backtest, and still impressive as an autoresearch system.


-----


Below are **real current Kalshi market examples** I found, with **sample inputs/outputs your autoresearch system would produce**. The market names/tickers are real/current from Kalshi pages; the model probabilities, edges, and decisions below are **example system outputs**, not trade recommendations.

Kalshi’s public market-data API can fetch market lists, events, and orderbooks without authentication, and its docs show `GET /markets`, `GET /events/{event_ticker}`, and `GET /markets/{ticker}/orderbook` as the basic flow. Kalshi’s orderbook API returns bids for YES and NO rather than explicit asks, because a YES ask can be inferred from the NO bid, and vice versa. ([Kalshi API Documentation][1])

---

# Example 1: Weather market — San Francisco high temperature

Real current market found:

**Market:** “Highest temperature in San Francisco today?”
**Ticker from URL:** `kxhightsfo-26may30`
Kalshi page says this market tracks San Francisco’s highest temperature for May 30, 2026. ([Kalshi][2])

## System input

```json
{
  "market_url": "kalshi://markets/kxhightsfo-26may30",
  "market_title": "Highest temperature in San Francisco today?",
  "category": "climate/weather",
  "research_mode": "paper_trade_only",
  "max_position_usd": 25,
  "edge_threshold": 0.06,
  "required_sources": [
    "Kalshi market metadata",
    "Kalshi orderbook",
    "NWS forecast",
    "NOAA/NWS observed temperature",
    "historical station data"
  ]
}
```

## Agent workflow

```text
1. Fetch market metadata.
2. Parse resolution rule:
   - What station?
   - What date?
   - What source resolves the final temperature?
   - What exact temperature bucket is this contract?
3. Fetch orderbook.
4. Pull NWS forecast and hourly observations.
5. Estimate probability distribution over high temperature.
6. Compare each bucket's fair probability to market price.
7. Reject buckets with unclear resolution, low liquidity, or poor edge.
```

## Example internal model output

```json
{
  "forecast_distribution_fahrenheit": {
    "<=62": 0.03,
    "63-64": 0.12,
    "65-66": 0.41,
    "67-68": 0.31,
    "69-70": 0.10,
    "71+": 0.03
  },
  "model_notes": [
    "Weather market is strong for autoresearch because resolution is objective.",
    "Main uncertainty is final observed station high vs public forecast high.",
    "Late-day observation updates matter more than news search."
  ]
}
```

## Example trade-decision output

```json
{
  "market": "Highest temperature in San Francisco today?",
  "ticker": "kxhightsfo-26may30",
  "candidate_contract": "65-66°F",
  "market_yes_ask": 0.34,
  "model_probability_yes": 0.41,
  "estimated_fee_and_slippage": 0.025,
  "net_edge": 0.045,
  "decision": "WATCHLIST_ONLY",
  "reason": "Model edge is positive but below required 6-point threshold after fees/slippage.",
  "risk_flags": [
    "Weather observation can update late",
    "Bucket market: adjacent buckets are highly correlated",
    "Need station-specific observed data, not generic city forecast"
  ],
  "human_readable_memo": "The agent estimates the 65-66°F bucket at 41% versus a sample market ask of 34%. After estimated costs, edge is only 4.5 percentage points, below the configured threshold. No trade."
}
```

This is probably the **best MVP domain** because the model is grounded in structured data, not vague news sentiment.

---

# Example 2: Weather binary — NYC rain today

Real current market found:

**Market:** “Will it rain in NYC today?”
**Ticker from URL:** `kxrainnyc-26may30`
The Kalshi page refers to the NYC rain market for May 30, 2026 and mentions resolution using climatological report references if needed. ([Kalshi][3])

## System input

```json
{
  "market_url": "kalshi://markets/kxrainnyc-26may30",
  "market_title": "Will it rain in NYC today?",
  "category": "climate/weather",
  "target": "binary_yes_no",
  "research_mode": "paper_trade_only",
  "model_type": "precipitation_nowcast"
}
```

## Agent workflow

```text
1. Parse resolution rule:
   - Does drizzle count?
   - What measurement threshold counts as rain?
   - Which station/report determines resolution?
2. Pull:
   - NWS hourly forecast
   - Radar/precipitation nowcast
   - Station observations
   - Historical same-date rainfall base rate
3. Estimate P(rain by resolution criteria).
4. Compare to YES/NO orderbook.
```

## Example output

```json
{
  "market": "Will it rain in NYC today?",
  "ticker": "kxrainnyc-26may30",
  "resolution_summary": {
    "event": "Rain in NYC on May 30, 2026",
    "source_type": "official weather/climatological report",
    "ambiguity_score": "medium",
    "ambiguity_reason": "Need exact station/report and minimum measurable precipitation threshold."
  },
  "model_probability_yes": 0.27,
  "market_yes_ask": 0.39,
  "market_no_ask": 0.64,
  "estimated_fee_and_slippage": 0.03,
  "net_edge_yes": -0.15,
  "net_edge_no": 0.06,
  "decision": "PAPER_BUY_NO",
  "position_size_usd": 10,
  "confidence": "medium",
  "risk_flags": [
    "Weather markets can move quickly near precipitation events",
    "Resolution depends on exact source",
    "Avoid real execution until station/rule parser is verified"
  ],
  "memo": "The model estimates rain at 27%. The sample market YES ask is 39%, implying the market is pricing rain higher than the model. The NO side has a sample net edge of about 6 points, so the paper-trading system records a small NO position."
}
```

This example shows why your system needs a **resolution-rule parser** before modeling. “Rain in NYC” sounds simple, but the edge depends on the exact official source and threshold.

---

# Example 3: Economics — CPI in June 2026

Real current market found:

**Market:** “CPI in June”
**Ticker from URL:** `kxcpi-26jun`
Kalshi’s page says the market resolves YES if CPI increases by more than `0.4%` in June 2026, with outcome verified from the Bureau of Labor Statistics. ([Kalshi][4])

The BLS describes CPI as measuring the average change over time in prices paid by urban consumers, and its current CPI page shows the April 2026 CPI release context, including April’s 0.6% seasonally adjusted monthly increase and 3.8% year-over-year increase. ([Bureau of Labor Statistics][5])

## System input

```json
{
  "market_url": "kalshi://markets/kxcpi-26jun",
  "market_title": "CPI in June",
  "resolution_target": "CPI m/m > 0.4%",
  "official_source": "BLS CPI release",
  "category": "economics",
  "research_mode": "paper_trade_only",
  "data_sources": [
    "BLS CPI release calendar",
    "Cleveland Fed inflation nowcast",
    "gasoline prices",
    "used car indexes",
    "rent/shelter trend",
    "food/energy components",
    "market consensus"
  ]
}
```

## Agent workflow

```text
1. Parse resolution:
   - Is it headline CPI?
   - Is it seasonally adjusted?
   - Is threshold strictly >0.4 or >=0.4?
   - Is it rounded to one decimal?
2. Pull macro indicators.
3. Build component-level CPI nowcast:
   - shelter
   - energy
   - food
   - core goods
   - core services
4. Convert nowcast distribution to P(CPI > 0.4%).
5. Compare against market price.
```

## Example output

```json
{
  "market": "CPI in June",
  "ticker": "kxcpi-26jun",
  "resolution_summary": {
    "metric": "Consumer Price Index",
    "period": "June 2026",
    "threshold": "> 0.4%",
    "source": "BLS",
    "critical_rule_question": "Whether value is rounded to one decimal before threshold comparison"
  },
  "component_nowcast": {
    "shelter_contribution": 0.16,
    "energy_contribution": 0.13,
    "food_contribution": 0.04,
    "core_goods_contribution": 0.02,
    "core_services_ex_shelter_contribution": 0.09,
    "headline_cpi_mom_mean": 0.44,
    "headline_cpi_mom_std": 0.12
  },
  "model_probability_yes": 0.57,
  "market_yes_ask": 0.49,
  "estimated_fee_and_slippage": 0.035,
  "net_edge": 0.045,
  "decision": "WATCHLIST_ONLY",
  "reason": "Positive model edge but below threshold. Wait for more component data or better price.",
  "risk_flags": [
    "Macro releases are highly competitive",
    "Rounding rule matters",
    "Energy/gasoline shocks can dominate headline CPI",
    "Model uncertainty is large before full month data is available"
  ],
  "memo": "The system estimates a 57% probability that June CPI exceeds 0.4%, mainly because the component nowcast is centered around 0.44%. The sample market ask is 49%, but after fees and slippage the edge is not large enough."
}
```

This is a good **medium-difficulty** market for your agent. It combines structured data, calendar events, and quantitative nowcasting.

---

# Example 4: Economics — Jobs numbers in June 2026

Real current market found:

**Market:** “Jobs numbers in June 2026?”
**Ticker from URL:** `kxpayrolls-26jun`
Kalshi has a current page for this jobs-number market. ([Kalshi][6])

## System input

```json
{
  "market_url": "kalshi://markets/kxpayrolls-26jun",
  "market_title": "Jobs numbers in June 2026?",
  "category": "economics",
  "official_source": "BLS Employment Situation release",
  "research_mode": "paper_trade_only",
  "data_sources": [
    "ADP employment",
    "initial jobless claims",
    "continuing claims",
    "ISM employment components",
    "regional Fed surveys",
    "market consensus",
    "prior payroll revisions"
  ]
}
```

## Example output

```json
{
  "market": "Jobs numbers in June 2026?",
  "ticker": "kxpayrolls-26jun",
  "resolution_summary": {
    "metric": "Nonfarm payrolls",
    "period": "June 2026",
    "source": "BLS",
    "unit": "thousands of jobs",
    "resolution_risk": "medium"
  },
  "model_forecast_distribution": {
    "<0k": 0.08,
    "0k_to_74k": 0.18,
    "75k_to_149k": 0.34,
    "150k_to_224k": 0.25,
    "225k+": 0.15
  },
  "candidate_contract": "75k_to_149k",
  "model_probability_yes": 0.34,
  "market_yes_ask": 0.29,
  "estimated_fee_and_slippage": 0.025,
  "net_edge": 0.025,
  "decision": "NO_TRADE",
  "reason": "The raw edge is too small and payroll markets have high forecast uncertainty.",
  "risk_flags": [
    "Payroll revisions can matter depending on exact contract rules",
    "Consensus estimates can move close to release",
    "Labor data surprises are hard to model from public data alone"
  ]
}
```

For this market, the research system should be more conservative than for weather. The right output is often **“no trade”**, which is good. A useful agent filters aggressively.

---

# Example 5: Fed market — June 2026 Fed combo

Real current market found:

**Market:** “June 2026 Fed Combo: Rate and Dissents”
**Ticker from URL:** `kxfedcombo-26jun`
Kalshi has a current page for this June 2026 Fed combo market. ([Kalshi][7])

## System input

```json
{
  "market_url": "kalshi://markets/kxfedcombo-26jun",
  "market_title": "June 2026 Fed Combo: Rate and Dissents",
  "category": "economics/rates",
  "research_mode": "paper_trade_only",
  "data_sources": [
    "FOMC calendar",
    "Fed funds futures",
    "SOFR curve",
    "CPI",
    "payrolls",
    "unemployment",
    "Fed speeches",
    "FOMC statement history"
  ]
}
```

## Example output

```json
{
  "market": "June 2026 Fed Combo: Rate and Dissents",
  "ticker": "kxfedcombo-26jun",
  "resolution_summary": {
    "event": "June 2026 FOMC decision",
    "dimensions": ["rate decision", "dissent count"],
    "complexity": "high",
    "reason": "Multi-dimensional outcome: rate action and voting dissents are correlated but not identical."
  },
  "model_probabilities": {
    "hold_no_dissents": 0.42,
    "hold_one_or_more_dissents": 0.24,
    "hike_no_dissents": 0.11,
    "hike_with_dissents": 0.08,
    "cut_no_dissents": 0.10,
    "cut_with_dissents": 0.05
  },
  "candidate_contract": "hold_one_or_more_dissents",
  "model_probability_yes": 0.24,
  "market_yes_ask": 0.19,
  "estimated_fee_and_slippage": 0.025,
  "net_edge": 0.025,
  "decision": "NO_TRADE",
  "reason": "The apparent edge is weak, and the contract is complex. Agent needs better historical dissent model before trading.",
  "risk_flags": [
    "Fed communication can change quickly",
    "Dissent outcome is less liquid and harder to model than rate decision",
    "Do not use non-public institutional information"
  ]
}
```

This is a good example of where an LLM can help parse speeches and statements, but the final probability should come from a structured model.

---

# Example 6: Crypto — Bitcoin price at end of 2026

Real current market found:

**Market:** “Bitcoin price at the end of 2026”
**Ticker from URL:** `kxbtcy-27jan0100`
Kalshi has a current page for this Bitcoin end-of-2026 price market. ([Kalshi][8])

## System input

```json
{
  "market_url": "kalshi://markets/kxbtcy-27jan0100",
  "market_title": "Bitcoin price at the end of 2026",
  "category": "crypto",
  "research_mode": "paper_trade_only",
  "data_sources": [
    "spot BTC price",
    "BTC volatility surface",
    "BTC ETF flows",
    "realized volatility",
    "macro liquidity indicators",
    "on-chain supply metrics",
    "Kalshi orderbook"
  ]
}
```

## Example output

```json
{
  "market": "Bitcoin price at the end of 2026",
  "ticker": "kxbtcy-27jan0100",
  "resolution_summary": {
    "asset": "Bitcoin",
    "event": "End-of-year 2026 price range",
    "resolution_risk": "medium",
    "key_question": "Which exchange/index price is used for final settlement?"
  },
  "model_distribution": {
    "<75000": 0.16,
    "75000_to_100000": 0.24,
    "100000_to_125000": 0.25,
    "125000_to_150000": 0.17,
    "150000_to_200000": 0.12,
    "200000+": 0.06
  },
  "candidate_contract": "100000_to_125000",
  "model_probability_yes": 0.25,
  "market_yes_ask": 0.31,
  "estimated_fee_and_slippage": 0.03,
  "net_edge": -0.09,
  "decision": "REJECT",
  "reason": "Market price is richer than model fair probability.",
  "risk_flags": [
    "Long time horizon",
    "High volatility",
    "Large macro/regulatory uncertainty",
    "Resolution-index details matter"
  ]
}
```

Crypto markets are attractive because data is plentiful, but they are hard because the outcome distribution is extremely fat-tailed.

---

# Example 7: Sports/event market — PSG vs Arsenal Champions League method of finish

Real current market found:

**Market:** “PSG vs Arsenal: Method of Finish — Champions League”
**Ticker from URL:** `kxuclmof-26may30psgars`
The Kalshi page says this market concerns how the PSG vs Arsenal Champions League Final, scheduled for May 30, 2026, is decided. ([Kalshi][9])

## System input

```json
{
  "market_url": "kalshi://markets/kxuclmof-26may30psgars",
  "market_title": "PSG vs Arsenal: Method of Finish",
  "category": "sports",
  "research_mode": "paper_trade_only",
  "data_sources": [
    "sports odds markets",
    "team Elo",
    "injury reports",
    "lineups",
    "recent match stats",
    "extra-time and penalty historical rates"
  ]
}
```

## Example output

```json
{
  "market": "PSG vs Arsenal: Method of Finish",
  "ticker": "kxuclmof-26may30psgars",
  "model_probabilities": {
    "decided_in_regular_time": 0.73,
    "decided_in_extra_time": 0.09,
    "decided_by_penalties": 0.18
  },
  "candidate_contract": "decided_by_penalties",
  "model_probability_yes": 0.18,
  "market_yes_ask": 0.22,
  "estimated_fee_and_slippage": 0.025,
  "net_edge": -0.065,
  "decision": "REJECT",
  "reason": "The sample market ask is higher than model fair value after costs.",
  "risk_flags": [
    "Sports markets are highly competitive",
    "Lineup news can move prices fast",
    "Model needs external odds comparison",
    "Liquidity and fees can erase small edges"
  ]
}
```

For a hackathon, I would include sports only as a demo category. For real modeling, I would start with weather/economic data because they are more objectively researchable.

---

# What the full system output should look like

For any market, your system should produce one standard object:

```json
{
  "run_id": "research_2026_05_30_001",
  "timestamp_utc": "2026-05-30T18:00:00Z",
  "venue": "kalshi",
  "market_ticker": "kxcpi-26jun",
  "market_title": "CPI in June",
  "category": "economics",
  "status": "open",
  "resolution": {
    "summary": "Resolves YES if June 2026 CPI m/m is greater than 0.4%.",
    "official_source": "BLS",
    "ambiguity_score": "medium",
    "unresolved_questions": [
      "Is the comparison based on rounded one-decimal CPI?",
      "What happens if BLS revises the initial number?"
    ]
  },
  "market_data": {
    "yes_bid": 0.46,
    "yes_ask": 0.49,
    "no_bid": 0.51,
    "no_ask": 0.54,
    "spread": 0.03,
    "top_level_liquidity_contracts": 1200
  },
  "model": {
    "model_probability_yes": 0.57,
    "confidence": "medium",
    "model_family": "component_nowcast_plus_bayesian_update",
    "main_features": [
      "gasoline contribution",
      "shelter trend",
      "core services trend",
      "prior CPI momentum"
    ]
  },
  "edge": {
    "raw_edge": 0.08,
    "estimated_fee": 0.02,
    "estimated_slippage": 0.015,
    "net_edge": 0.045
  },
  "decision": {
    "action": "WATCHLIST_ONLY",
    "reason": "Positive but insufficient edge after fees/slippage.",
    "max_position_usd": 0,
    "paper_trade": false
  },
  "risk": {
    "risk_score": 6,
    "flags": [
      "macro data uncertainty",
      "possible rounding ambiguity",
      "large price movement near release"
    ]
  },
  "audit": {
    "sources_used": [
      "Kalshi market page",
      "Kalshi orderbook",
      "BLS CPI page",
      "inflation nowcast data"
    ],
    "llm_used_for": [
      "resolution parsing",
      "source summarization",
      "risk memo"
    ],
    "code_used_for": [
      "probability estimate",
      "fee calculation",
      "edge calculation",
      "decision rule"
    ]
  }
}
```

---

# The most important design pattern

Separate the system into **research**, **modeling**, **decision**, and **execution**.

```text
Research Agent:
  "What is this market actually asking?"

Data Agent:
  "What public data can answer it?"

Model Agent:
  "What is the fair probability?"

Risk Agent:
  "Can we trust this enough to act?"

Execution Agent:
  "Only paper trade or place a capped limit order."
```

Kalshi’s fee schedule matters because the expected edge has to survive fees. The official fee document says general trade fees are calculated as `round up(0.07 × C × P × (1-P))`, where `C` is contract count and `P` is contract price in dollars, with maker fees listed separately. ([Kalshi][10])

So your agent’s core decision should look like this:

```python
def should_trade(model_p, yes_ask, fee, slippage, min_edge=0.06):
    net_edge = model_p - yes_ask - fee - slippage

    if net_edge < min_edge:
        return {
            "decision": "NO_TRADE",
            "net_edge": net_edge,
            "reason": "Edge below threshold after costs"
        }

    return {
        "decision": "PAPER_TRADE_OR_LIMIT_ORDER",
        "net_edge": net_edge,
        "reason": "Positive edge after fees/slippage"
    }
```

For your first real build, I would implement these three market families in order:

```text
1. Weather markets
   Best for MVP: objective, frequent, structured, easy to backtest.

2. CPI / payrolls / Fed markets
   Better for serious research: fewer events, but rich data and high interest.

3. Crypto / sports
   Good for demo breadth, but harder to find durable edge.
```

[1]: https://docs.kalshi.com/getting_started/quick_start_market_data "Quick Start: Market Data - API Documentation"
[2]: https://kalshi.com/markets/kxhightsfo/san-francisco-high-temperature-daily/kxhightsfo-26may30?utm_source=chatgpt.com "Highest temperature in San Francisco today? Odds & ..."
[3]: https://kalshi.com/markets/kxrainnyc/nyc-rain/kxrainnyc-26may30?utm_source=chatgpt.com "Will it rain in NYC today? Odds & Predictions 2026"
[4]: https://kalshi.com/markets/kxcpi/cpi/kxcpi-26jun?utm_source=chatgpt.com "CPI in June Odds & Predictions 2026"
[5]: https://www.bls.gov/cpi/?utm_source=chatgpt.com "CPI Home : U.S. Bureau of Labor Statistics"
[6]: https://kalshi.com/markets/kxpayrolls/jobs-numbers/kxpayrolls-26jun?utm_source=chatgpt.com "Jobs numbers in June 2026? Odds & Predictions"
[7]: https://kalshi.com/markets/kxfedcombo/fed-combo/kxfedcombo-26jun?utm_source=chatgpt.com "June 2026 Fed Combo: Rate and Dissents"
[8]: https://kalshi.com/markets/kxbtcy/btc-price-range-eoy/kxbtcy-27jan0100?utm_source=chatgpt.com "Bitcoin price at the end of 2026 Odds & Predictions"
[9]: https://kalshi.com/markets/kxuclmof/ucl-method-of-finish/kxuclmof-26may30psgars?utm_source=chatgpt.com "PSG vs Arsenal: Method of Finish - Champions League"
[10]: https://kalshi.com/docs/kalshi-fee-schedule.pdf?utm_source=chatgpt.com "Fee Schedule for Feb 2026"
