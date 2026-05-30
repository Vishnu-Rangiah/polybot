# Weather Research MVP

This document explains the root-level Kalshi weather research scaffold:

```text
research.py      -> core market/weather research logic
modal_app.py     -> parallel execution wrapper around research.py
agent_runner.py  -> OpenAI Agents SDK coordinator
ledger.jsonl     -> append-only local run history, ignored by git
```

The MVP is paper-only. It reads public market/weather data, estimates a simple fair probability, and prints a research memo. It does not place trades and does not use private Kalshi keys.

## Mental Model

The system is intentionally split into deterministic code plus an agent coordinator:

```text
Ticker
  -> research_market(ticker)
    -> Kalshi public market API
    -> Kalshi public orderbook API
    -> orderbook normalizer
    -> weather market parser
    -> NWS hourly forecast API
    -> probability heuristic
    -> edge and decision engine
    -> JSON memo

Optional wrappers:
  -> Modal maps research_market over many tickers
  -> OpenAI agent calls research tools and summarizes results
  -> ledger.jsonl records compact run summaries
```

The important design choice is that the OpenAI agent does not invent the market data or edge calculation. The Python functions do that work. The agent only chooses which tool to call and writes the final human-readable summary.

## Setup

Install dependencies:

```bash
uv sync
```

This project is pinned to Python 3.11 with:

```text
.python-version
pyproject.toml requires-python = ">=3.11,<3.14"
```

The Python upper bound avoids package build issues seen with Python 3.14 and Modal's dependency chain. `cbor2<6` is pinned because the newer major version required a Rust compiler on this machine.

## Local Research Flow

Run one live market locally:

```bash
uv run python research.py --ticker KXRAINNYC-26MAY31-T0
```

Run without writing to the ledger:

```bash
uv run python research.py --ticker KXRAINNYC-26MAY31-T0 --no-ledger
```

The output is JSON shaped like:

```json
{
  "market_ticker": "KXRAINNYC-26MAY31-T0",
  "market_title": "Will it **rain** in New York City on Sunday?",
  "market_data": {
    "yes_bid": 0.04,
    "yes_ask": 0.26,
    "no_bid": 0.74,
    "no_ask": 0.96,
    "liquidity": 31.0
  },
  "model": {
    "probability_yes": 0.007,
    "confidence": "medium",
    "notes": [
      "Max hourly precipitation probability: 1%",
      "Average hourly precipitation probability: 0%",
      "Heuristic treats weather hours as correlated."
    ]
  },
  "decision": {
    "action": "NO_TRADE",
    "raw_edge": -0.253,
    "net_edge": -0.293,
    "reason": "Edge is below threshold after estimated costs."
  },
  "paper_trade_only": true
}
```

## Core Code Path

The public API inside `research.py` is:

```python
from research import research_market

result = research_market("KXRAINNYC-26MAY31-T0")
print(result["decision"]["action"])
print(result["model"]["probability_yes"])
```

Internally, `research_market()` performs these steps:

```python
def research_market(ticker: str) -> dict:
    normalized_ticker = ticker.upper()
    market = fetch_kalshi_market(normalized_ticker)
    orderbook = fetch_kalshi_orderbook(normalized_ticker)
    market_data = normalize_orderbook(orderbook)
    rule = parse_weather_rule(market)

    location_key = rule.get("location")
    if location_key not in KNOWN_LOCATIONS:
        model = {
            "probability_yes": 0.5,
            "confidence": "low",
            "notes": ["Location is unsupported by the MVP weather map."],
        }
    else:
        hourly = fetch_nws_hourly_forecast(KNOWN_LOCATIONS[location_key])
        model = estimate_probability(rule, hourly)

    decision = decide(
        model_p=model["probability_yes"],
        market_data=market_data,
        ambiguity_score=rule["ambiguity_score"],
    )
```

That means debugging is straightforward:

1. If Kalshi fetch fails, inspect `fetch_kalshi_market()` or `fetch_kalshi_orderbook()`.
2. If asks look wrong, inspect `normalize_orderbook()`.
3. If the market is unsupported, inspect `parse_weather_rule()` and `KNOWN_LOCATIONS`.
4. If the probability looks wrong, inspect `estimate_rain_probability()` or `estimate_high_temp_probability()`.
5. If the final action looks wrong, inspect `decide()`.

## Kalshi Orderbook Normalization

Kalshi orderbooks provide YES bids and NO bids. The MVP infers asks:

```python
yes_ask = 1.0 - best_no_bid
no_ask = 1.0 - best_yes_bid
```

In code:

```python
def normalize_orderbook(orderbook: dict) -> dict:
    yes_levels = orderbook.get("yes_dollars") or orderbook.get("yes") or []
    no_levels = orderbook.get("no_dollars") or orderbook.get("no") or []
    yes_bid, yes_qty = _best_bid(yes_levels)
    no_bid, no_qty = _best_bid(no_levels)

    yes_ask = None if no_bid is None else round(1.0 - no_bid, 4)
    no_ask = None if yes_bid is None else round(1.0 - yes_bid, 4)
```

The helper accepts both decimal prices like `0.74` and cent prices like `74`.

## Weather Parsing

The MVP parser is deliberately simple. It looks at ticker, event ticker, series ticker, title, and subtitle.

Currently supported families:

```text
weather_rain
weather_high_temp
unsupported
```

Example:

```python
if "rain" in text or "precip" in text:
    return {
        "market_family": "weather_rain",
        "location": location,
        "metric": "precipitation",
        "threshold": "measurable rain; exact threshold must be checked in Kalshi rules",
        "ambiguity_score": "medium",
        "unresolved_questions": [
            "Which station or official report controls settlement?",
            "What minimum precipitation amount counts as rain?",
        ],
    }
```

Known locations are hard-coded for the demo:

```python
KNOWN_LOCATIONS = {
    "NYC": {"lat": 40.7812, "lon": -73.9665},
    "SFO": {"lat": 37.7749, "lon": -122.4194},
}
```

To add a new city, add a location entry and update `infer_location()`.

## Probability Heuristic

Rain markets use NWS hourly precipitation probability:

```python
max_pop = max(pops)
avg_pop = sum(pops) / len(pops)
probability = 0.65 * max_pop + 0.35 * avg_pop
```

This is intentionally transparent, not sophisticated. It treats weather hours as correlated and gives more weight to the highest hourly rain probability.

High-temperature markets use the max NWS hourly forecast temperature and compare it to the parsed bucket. If the bucket is unclear, the model returns a neutral `0.5` with low confidence.

## Decision Logic

The decision engine compares model probability to the inferred market ask:

```python
raw_edge = model_probability_yes - yes_ask
net_edge = raw_edge - estimated_fee - estimated_slippage
```

Current actions:

```text
NO_TRADE        -> edge is too low, data is ambiguous, or ask is missing
WATCHLIST_ONLY  -> liquidity is too thin
PAPER_BUY_YES   -> model clears YES ask by at least 6 percentage points after costs
```

The output is always paper-only:

```json
{
  "paper_trade_only": true
}
```

## Ledger

By default, local and agent runs append a compact summary to `ledger.jsonl`.

Example programmatic use:

```python
from pathlib import Path
from research import append_ledger_entry, research_market

result = research_market("KXRAINNYC-26MAY31-T0")
append_ledger_entry(result, path=Path("ledger.jsonl"))
```

Example ledger row:

```json
{
  "timestamp_utc": "2026-05-30T19:55:44.203692+00:00",
  "run_type": "live_weather_research",
  "run_id": "research_20260530T195336Z_KXRAINNYC-26MAY31-T0",
  "ticker": "KXRAINNYC-26MAY31-T0",
  "model_probability_yes": 0.007,
  "yes_ask": 0.26,
  "net_edge": -0.293,
  "action": "NO_TRADE",
  "paper_trade_only": true
}
```

`ledger.jsonl` is ignored by git.

## Modal Parallel Execution

`modal_app.py` wraps the same `research_market()` function:

```python
@app.function(image=image, timeout=120)
def research_one_market(ticker: str) -> dict:
    from research import research_market

    return research_market(ticker)
```

Run multiple tickers in Modal:

```bash
uv run modal run modal_app.py --tickers KXRAINNYC-26MAY31-T0,KXRAINNYC-26MAY30-T0
```

Skip ledger writes from the local Modal entrypoint:

```bash
uv run modal run modal_app.py --tickers KXRAINNYC-26MAY31-T0 --no-write-ledger
```

Use the Modal wrapper from Python:

```python
from modal_app import research_many_markets

results = research_many_markets([
    "KXRAINNYC-26MAY31-T0",
    "KXRAINNYC-26MAY30-T0",
])
```

The `manage_app` flag exists because `modal run` already starts an app context:

```python
def research_many_markets(tickers, *, manage_app: bool = True) -> list[dict]:
    if not manage_app:
        return list(research_one_market.map(ticker_list))

    with app.run():
        return list(research_one_market.map(ticker_list))
```

## OpenAI Agent Coordinator

`agent_runner.py` defines an agent with two tools:

```python
@function_tool
def research_market_tool(ticker: str) -> dict:
    """Research one Kalshi weather market and return a paper-trade memo."""
    return research_market_payload(ticker)


@function_tool
def research_many_markets_tool(tickers: list[str]) -> list[dict]:
    """Research multiple Kalshi weather markets in parallel when Modal is enabled."""
    return research_many_markets_payload(tickers, use_modal=use_modal)
```

Run the agent sequentially without Modal:

```bash
OPENAI_API_KEY="$(< keys/openapi_key.txt)" uv run python agent_runner.py --local \
  "Research KXRAINNYC-26MAY31-T0 and KXRAINNYC-26MAY30-T0, then summarize the best paper-only watchlist candidates"
```

Run the agent with Modal enabled:

```bash
OPENAI_API_KEY="$(< keys/openapi_key.txt)" uv run python agent_runner.py \
  "Research KXRAINNYC-26MAY31-T0 and KXRAINNYC-26MAY30-T0, then summarize the best paper-only watchlist candidates"
```

Programmatic use:

```python
from agent_runner import run_agent

summary = run_agent(
    "Research KXRAINNYC-26MAY31-T0 and summarize the key risks.",
    use_modal=False,
)
print(summary)
```

The agent instructions require paper-only output:

```text
You must not place trades.
You must not access private keys.
You must label all outputs as paper research.
If resolution rules are ambiguous, mark NO_TRADE or WATCHLIST_ONLY.
```

## Safety Boundaries

The MVP has these intentional constraints:

```text
No order placement.
No private Kalshi key access.
No claim of profitability.
No hidden model-only trading decision.
No broad package restructure yet.
```

The only key used in agent runs is `OPENAI_API_KEY`, passed through the environment. Do not print it, log it, or move it into committed files.

## How To Extend

Add a new city:

1. Add coordinates to `KNOWN_LOCATIONS`.
2. Add ticker/title matching in `infer_location()`.
3. Run a known ticker through `research.py --no-ledger`.

Add a new weather family:

1. Add a parser branch in `parse_weather_rule()`.
2. Add a model branch in `estimate_probability()`.
3. Add explicit risk flags for settlement ambiguity.
4. Keep the output shape stable.

Improve the model:

1. Keep the current heuristic as a baseline.
2. Add more NWS fields or settlement-specific station data.
3. Return model notes that explain why the probability changed.
4. Compare decisions over time using `ledger.jsonl`.

Move into a package later:

```text
research.py      -> src/kalshi_agent/research.py or split modules
modal_app.py     -> src/kalshi_agent/modal_app.py
agent_runner.py  -> src/kalshi_agent/agent_runner.py
```

Do that after the demo path is stable, not before.

## Troubleshooting

If `uv sync` fails on Python 3.14, check that `.python-version` is set to `3.11` and that `pyproject.toml` still has `<3.14`.

If Kalshi or NWS calls fail in the sandbox, rerun with normal network access. The code uses public HTTPS APIs.

If Modal says the app is already running, make sure the local entrypoint calls:

```python
research_many_markets(tickers, manage_app=False)
```

If the agent cannot start, check that:

```bash
OPENAI_API_KEY="$(< keys/openapi_key.txt)" uv run python agent_runner.py --local "Research KXRAINNYC-26MAY31-T0"
```

is being run from the repo root and that `uv sync` has installed `openai-agents`.
