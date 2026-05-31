# Design: Kalshi Autoresearch Agent

## One-Line Pitch

Build an autonomous research system for prediction markets. The first demo researches live Kalshi weather markets from the terminal using public data and outputs paper-trade decisions. The deeper system lets an agent iterate on trading strategies against a frozen, no-lookahead backtester.

## Source Of Truth

This file is the canonical design source for the project. Supporting docs:

- `docs/CODE_LAYOUT.md` - current package layout and CLI commands.
- `docs/WEATHER_RESEARCH_MVP.md` - live weather research walkthrough.
- `docs/STRATEGY_AUTORESEARCH.md` - Codex/Modal strategy loop operations.
- `docs/MODAL_SANDBOX_WALKTHROUGH.md` - Modal sandbox smoke-test workflow.
- `.cursor/plans/kalshi_weather_agent_92ec1e3f.plan.md` - earlier implementation plan for the terminal weather MVP.

When docs disagree, follow this file first, then update the walkthrough that owns the affected command path.

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
- Public market data can be fetched without authentication from the canonical prod host `https://api.elections.kalshi.com/trade-api/v2`.
- Orderbooks return YES bids and NO bids, not explicit asks.
- `yes_ask = 1 - best_no_bid`.
- `no_ask = 1 - best_yes_bid`.
- Fees, spread, slippage, and thin liquidity can erase apparent edge.
- The MVP is paper-trade only. Authenticated trading should wait until the agent has evals, risk limits, and manual approval.

## Merged Product Direction

There are two complementary ideas in the repo:

1. **Live weather research agent:** Given a current Kalshi weather market, fetch market data and public weather evidence, estimate fair probability, and print an explainable paper-trade memo.
2. **Autoresearch backtesting loop:** Give an agent one mutable strategy module and a frozen backtester; let it iterate on strategies while validation metrics prevent overfitting.

These should merge into one product:

```text
Phase 1: Live Weather Research Agent
  - Pull current Kalshi weather market data.
  - Pull public Open-Meteo forecast data (settle ground truth on the NWS station Kalshi cites).
  - Produce explainable paper-trade recommendation.

Phase 2: Frozen Backtester
  - Replay resolved historical Kalshi markets.
  - Enforce no-lookahead and trading frictions.
  - Score strategies with PnL, Sharpe, Brier, n_trades, and max drawdown.

Phase 3: Autoresearch Loop
  - Agent edits only candidate strategy code.
  - `kalshi_agent/autoresearch/backtest.py` remains frozen.
  - `polybot loop` keeps or discards strategies using validation metrics.
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
  -> Open-Meteo client (live forecast + historical-forecast)
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

## Current Repo Layout

Package-first layout:

```text
polybot/
  README.md
  pyproject.toml
  docs/
    README.md
    CODE_LAYOUT.md
    DESIGN.md
  kalshi_agent/
    cli.py
    run.py
    types.py
    transport.py
    datasource.py
    kalshi_client.py
    kalshi_public.py
    weather.py
    research/
    autoresearch/
  outputs/
```

Runtime artifacts:

```text
strategies/
ledger.jsonl
strategy_ledger.jsonl
thesis.md
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
    "fair_prob_yes": 0.27,
    "resolution_ambiguity": "medium",
    "source_count": 3,
}
```

Example first strategy:

```python
def decide(state: MarketState) -> Order | None:
    model_p = state.features.get("fair_prob_yes")
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

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

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

### Weather Feature Source (Open-Meteo)

Implemented in `kalshi_agent/weather.py` as `MeteoSource`. It is a *feature*
source, not a `DataSource`: it produces the `features` dict (`fair_prob_yes` +
provenance) that `normalize()` folds into a `MarketState`, which `strategy.decide`
then reads. No API key, no signing — so it deliberately bypasses the Kalshi
`Transport`.

We use Open-Meteo instead of NWS for one decisive reason: **the backtest needs
the forecast as it stood at decision time `t`, and NWS does not archive past
forecasts.** Open-Meteo's Historical Forecast API archives past forecasts with
the same schema as the live feed, so the *same code* yields a live feature today
and a no-lookahead feature when replaying a resolved market. Live vs. historical
is a single switch — `as_of_date`:

```text
as_of_date is None  -> live forecast        api.open-meteo.com/v1/forecast
as_of_date is set    -> historical forecast  historical-forecast-api.open-meteo.com/v1/forecast
```

Two data realities that the code handles explicitly:

- **Coverage:** `precipitation_probability` is only archived from ~late 2024
  onward. Earlier dates return all-null, so backtests there get no signal.
- **No-signal must abstain, not guess.** When the window has no usable
  probabilities, `precip_features` emits `fair_prob_yes = None` (not `0.5`), so
  `decide` returns `None` and the strategy stays out. Treating missing data as a
  coin flip would silently trade on nothing.

Docs:
- Historical Forecast: https://open-meteo.com/en/docs/historical-forecast-api
- Previous Runs (fixed lead-time, stricter no-lookahead): https://open-meteo.com/en/docs/previous-runs-api
- Historical Weather / ERA5 (settlement approximation): https://open-meteo.com/en/docs/historical-weather-api

### Weather Probability Model

Transparent heuristic in `weather.py:rain_probability` — collapse the day's
hourly precipitation probabilities into one YES probability, weighting the peak
hour (a binary "did it rain today" market resolves on the peak, not the average)
while keeping some average mass:

```python
probability = 0.65 * max(hourly_pops) + 0.35 * mean(hourly_pops)
```

Settlement note: features can come from any forecast source, but the backtest's
**ground truth must match Kalshi's cited resolution station** (e.g. NYC settles
on NWS Central Park), not whatever we used for features. `WEATHER_LOCATIONS`
records the settlement source per location.

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
3. Pulls public Open-Meteo forecast data (live, or as-of-date for backtests).
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

- How much historical Kalshi price/orderbook data is available? (Resolved-market
  trades/candlesticks are available via the API; full orderbook history is not.)
- ~~Where do no-lookahead weather features come from?~~ Resolved: Open-Meteo
  Historical Forecast API archives past forecasts (`precipitation_probability`
  from ~late 2024). Settlement ground truth must still match Kalshi's cited
  station (see `weather.py:WEATHER_LOCATIONS`).
- Which live weather series should be the demo target? (NYC/CHI/MIA rain are
  wired in `WEATHER_LOCATIONS`.)
- Is Raindrop worth integrating before the terminal demo is stable?
