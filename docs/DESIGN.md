# Design: Kalshi Autoresearch Agent

## One-Line Pitch

Build an autonomous research system for prediction markets. The first demo researches live Kalshi weather markets from the terminal using public data and outputs paper-trade decisions. The deeper system lets an agent iterate on trading strategies against a frozen, no-lookahead backtester.

## Source Of Truth

This file is the canonical design source for the project. Supporting docs:

- `docs/TASKS.md` - team coordination and task ownership.
- `kalshi_strats.md` - strategy catalog and example market outputs.
- `hackathon.md` - judging criteria, logistics, and resource links.
- `.cursor/plans/kalshi_weather_agent_92ec1e3f.plan.md` - earlier implementation plan for the terminal weather MVP.

When docs disagree, follow this file first, then update `docs/TASKS.md`.

## Hackathon Framing

The project should be pitched as **Applied Autonomous Research** with strong secondary hooks in **Retrieval & Knowledge Synthesis** and **Agent Architectures & Control Loops**.

Judges should see:

- A real end-to-end research loop, not just a chatbot.
- Structured retrieval from Kalshi and public data sources.
- Explicit probability modeling and risk checks.
- A repeatable path toward evals and backtesting.
- Clear demo output that non-experts can understand.

## Kalshi Basics

Kalshi is a regulated prediction market where users trade event contracts.

Examples:

```text
Will it rain in NYC today?
Will CPI be above 0.4%?
Will Bitcoin be above $100k at year end?
```

Most contracts are binary:

- `YES` pays `$1` if the event happens.
- `NO` pays `$1` if the event does not happen.
- A price of `0.37` roughly means the market is pricing the event near `37%`, before fees, spread, liquidity, and settlement risk.

Important Kalshi mechanics for this project:

- The market title is not enough. The exact resolution rule controls settlement.
- Public market data can be fetched without authentication from `https://external-api.kalshi.com/trade-api/v2`.
- Orderbooks return YES bids and NO bids, not explicit asks.
- `yes_ask = 1 - best_no_bid`.
- `no_ask = 1 - best_yes_bid`.
- Fees, spread, slippage, and thin liquidity can erase apparent edge.
- The MVP is paper-trade only. Authenticated trading should wait until the agent has evals, risk limits, and manual approval.

## Merged Product Direction

There are two complementary ideas in the repo:

1. **Live weather research agent:** Given a current Kalshi weather market, fetch market data and public weather evidence, estimate fair probability, and print an explainable paper-trade memo.
2. **Autoresearch backtesting loop:** Give an agent one mutable `strategy.py` and a frozen `backtest.py`; let it iterate on strategies while validation metrics prevent overfitting.

These should merge into one product:

```text
Phase 1: Live Weather Research Agent
  - Pull current Kalshi weather market data.
  - Pull public NWS data.
  - Produce explainable paper-trade recommendation.

Phase 2: Frozen Backtester
  - Replay resolved historical Kalshi markets.
  - Enforce no-lookahead and trading frictions.
  - Score strategies with PnL, Sharpe, Brier, n_trades, and max drawdown.

Phase 3: Autoresearch Loop
  - Agent edits only strategy.py.
  - backtest.py remains frozen.
  - loop.py keeps or discards strategies using validation metrics.
  - ledger.json records every attempt.

Phase 4: Demo Polish
  - Show one live weather-market memo.
  - Show backtest/ledger results if available.
  - Show Raindrop traces if time permits.
```

## Build Order Decision

The only real conflict between the existing plans is build order.

The teammate design starts with historical data and a rigorous backtester. This is more credible, but slower to demo.

The weather-agent plan starts with live public data and a terminal memo. This is faster to demo, but not yet a proven strategy.

Decision:

```text
Build the live weather terminal MVP first.
Do not claim it is a proven profitable strategy.
Then add the frozen backtester as the credibility layer.
```

## Architecture

```text
User enters Kalshi weather ticker
  -> Kalshi public market client
  -> market metadata + orderbook
  -> orderbook normalizer
  -> weather rule parser
  -> NWS data client
  -> weather probability model
  -> decision engine
  -> terminal JSON + human-readable memo
```

Later, the same `MarketState` produced by the live weather agent can feed the strategy/backtest loop:

```text
thesis.md
  -> agent edits strategy.py
  -> frozen backtest.py scores strategy
  -> train/val/test split prevents overfitting
  -> ledger.json records every attempt
  -> best strategy can be paper-traded
```

## Initial Repo Layout

Target layout:

```text
polybot/
  README.md
  requirements.txt
  docs/
    README.md
    DESIGN.md
    TASKS.md
  src/
    kalshi_agent/
      __init__.py
      cli.py
      types.py
      kalshi_client.py
      pricing.py
      rule_parser.py
      nws_client.py
      weather_model.py
      decision.py
      report.py
      strategy.py
  evals/
    golden_cases.json
  outputs/
    .gitkeep
```

Later additions:

```text
data/
  fetch.py
  cache/
backtest.py
loop.py
ledger.json
thesis.md
raindrop/
```

## Shared Contract

Both the live terminal agent and the later backtester should share the same core types.

```python
from dataclasses import dataclass

@dataclass
class MarketState:
    ticker: str
    title: str
    series_ticker: str | None
    category: str | None
    yes_bid: float | None
    yes_ask: float | None
    no_bid: float | None
    no_ask: float | None
    volume: float | None
    liquidity: float
    time_to_close_seconds: float | None
    features: dict

@dataclass
class Order:
    side: str
    size: int
    limit_price: float

@dataclass
class Metrics:
    pnl: float
    sharpe: float
    brier: float
    n_trades: int
    max_dd: float
```

Example weather features:

```python
features = {
    "market_family": "weather_rain",
    "location": "NYC",
    "nws_probability_yes": 0.27,
    "resolution_ambiguity": "medium",
    "source_count": 3,
}
```

Example first strategy:

```python
def decide(state: MarketState) -> Order | None:
    model_p = state.features.get("nws_probability_yes")
    if model_p is None or state.yes_ask is None:
        return None

    estimated_cost = 0.03
    min_edge = 0.06
    net_edge = model_p - state.yes_ask - estimated_cost

    if net_edge < min_edge:
        return None

    return Order(side="yes", size=1, limit_price=state.yes_ask)
```

## Live Weather MVP

### Kalshi Client

Use public endpoints first.

```python
import requests

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

class KalshiClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")

    def get_market(self, ticker: str) -> dict:
        response = requests.get(f"{self.base_url}/markets/{ticker}", timeout=15)
        response.raise_for_status()
        return response.json()["market"]

    def get_orderbook(self, ticker: str, depth: int = 5) -> dict:
        response = requests.get(
            f"{self.base_url}/markets/{ticker}/orderbook",
            params={"depth": depth},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["orderbook_fp"]
```

### Orderbook Normalization

```python
def best_level(levels: list[list[str]]) -> tuple[float | None, float]:
    if not levels:
        return None, 0.0
    price, quantity = levels[0]
    return float(price), float(quantity)

def normalize_orderbook(orderbook: dict) -> dict:
    yes_bid, yes_qty = best_level(orderbook.get("yes_dollars", []))
    no_bid, no_qty = best_level(orderbook.get("no_dollars", []))

    return {
        "yes_bid": yes_bid,
        "yes_ask": None if no_bid is None else round(1.0 - no_bid, 4),
        "no_bid": no_bid,
        "no_ask": None if yes_bid is None else round(1.0 - yes_bid, 4),
        "liquidity": yes_qty + no_qty,
    }
```

### NWS Client

The National Weather Service API requires a `User-Agent`.

```python
import requests

NWS_BASE_URL = "https://api.weather.gov"

class NWSClient:
    def __init__(self, user_agent: str):
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/geo+json",
        }

    def get_point_metadata(self, lat: float, lon: float) -> dict:
        response = requests.get(
            f"{NWS_BASE_URL}/points/{lat},{lon}",
            headers=self.headers,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["properties"]

    def get_hourly_forecast(self, lat: float, lon: float) -> list[dict]:
        point = self.get_point_metadata(lat, lon)
        response = requests.get(point["forecastHourly"], headers=self.headers, timeout=15)
        response.raise_for_status()
        return response.json()["properties"]["periods"]
```

### Weather Probability Model

Start with transparent heuristics.

```python
def estimate_rain_probability(hourly_periods: list[dict], hours_ahead: int = 18) -> dict:
    pops = []
    for period in hourly_periods[:hours_ahead]:
        value = period.get("probabilityOfPrecipitation", {}).get("value")
        if value is not None:
            pops.append(max(0.0, min(1.0, value / 100.0)))

    if not pops:
        return {
            "probability_yes": 0.5,
            "confidence": "low",
            "notes": ["NWS hourly precipitation probabilities were unavailable."],
        }

    max_pop = max(pops)
    avg_pop = sum(pops) / len(pops)
    probability = 0.65 * max_pop + 0.35 * avg_pop

    return {
        "probability_yes": round(probability, 3),
        "confidence": "medium",
        "notes": [
            f"Max hourly precipitation probability: {max_pop:.0%}",
            f"Average hourly precipitation probability: {avg_pop:.0%}",
            "Heuristic treats weather hours as correlated.",
        ],
    }
```

### Decision Engine

```python
def decide_yes_trade(model_p: float, yes_ask: float | None, liquidity: float) -> dict:
    if yes_ask is None:
        return {"action": "NO_TRADE", "reason": "No YES ask available."}

    estimated_fee = 0.02
    estimated_slippage = 0.02 if liquidity < 100 else 0.01
    min_edge = 0.06

    raw_edge = model_p - yes_ask
    net_edge = raw_edge - estimated_fee - estimated_slippage

    if liquidity < 25:
        action = "WATCHLIST_ONLY"
        reason = "Visible top-level liquidity is too low."
    elif net_edge >= min_edge:
        action = "PAPER_BUY_YES"
        reason = "Model probability clears market ask after costs."
    else:
        action = "NO_TRADE"
        reason = "Edge is below threshold after estimated costs."

    return {
        "action": action,
        "raw_edge": round(raw_edge, 4),
        "net_edge": round(net_edge, 4),
        "estimated_fee": estimated_fee,
        "estimated_slippage": estimated_slippage,
        "reason": reason,
    }
```

## Frozen Backtester

Once the live MVP works, add the teammate's backtesting architecture.

Contract:

```python
def backtest(strategy_fn, *, split: str) -> Metrics:
    """Run strategy_fn over train, val, or test and return comparable metrics."""
```

Rules:

- `strategy_fn` sees only data available before decision time `t`.
- Buying fills at ask; selling fills at bid.
- Slippage and liquidity caps come from recorded depth.
- Kalshi fees are included.
- Resolved outcomes are revealed only after market close.
- The agent may optimize on train.
- Keep/discard uses validation.
- Test is touched once at the end.

Metrics:

```text
pnl      realized dollars
sharpe   risk-adjusted return
brier    probability calibration
n_trades sample size guardrail
max_dd   survivability
```

Keep/discard rule:

```text
Keep iff val.sharpe beats rolling best
AND val.brier does not degrade
AND n_trades >= N_min
```

## Autoresearch Loop

The agent loop should mirror Karpathy-style autoresearch:

```text
read thesis.md
  -> edit strategy.py
  -> run backtest on train and val
  -> append result to ledger.json
  -> keep or discard
  -> repeat
```

Critical guardrail:

```text
The agent may edit strategy.py.
The agent must never edit backtest.py.
```

## Demo Plan

Minimum live demo:

```bash
python -m kalshi_agent.cli --ticker <weather-market-ticker>
```

Narration:

1. Fetches Kalshi market metadata and orderbook.
2. Parses the resolution question.
3. Pulls public NWS weather data.
4. Estimates fair probability.
5. Adjusts for fees, spread, slippage, and liquidity.
6. Prints a paper-trade decision with risk flags.

Stretch demo:

- Show an overfit strategy scoring well on train and failing on test.
- Show `ledger.json` from agent iterations.
- Show a Raindrop trace of thesis read, strategy edit, backtest call, and metrics.

## Guardrails

- Paper-trade only for the hackathon MVP.
- Never print or commit private Kalshi keys.
- Keep `keys/` and `.cursor/plans/` ignored.
- Mark unclear markets as `NO_TRADE`.
- Prefer transparent heuristics over unverifiable claims.
- Do not claim profitability before backtesting and forward paper testing.

## Open Questions

- How much historical Kalshi price/orderbook data is available?
- Can we fetch enough resolved weather markets for a credible backtest?
- Which live weather series should be the demo target?
- Is Raindrop worth integrating before the terminal demo is stable?
