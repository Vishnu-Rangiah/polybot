# Polybot Hackathon

Paper-only Kalshi weather-market research demo.

For a deeper walkthrough with code examples, see [`docs/WEATHER_RESEARCH_MVP.md`](docs/WEATHER_RESEARCH_MVP.md).

## Quick Start

Install dependencies:

```bash
uv sync
```

Run one local market research memo:

```bash
uv run python research.py --ticker KXRAINNYC-26MAY31-T0
```

Run several markets in parallel on Modal:

```bash
uv run modal run modal_app.py --tickers KXRAINNYC-26MAY31-T0,KXRAINNYC-26MAY30-T0
```

Run the OpenAI Agents SDK coordinator:

```bash
uv run python agent_runner.py --local "Research these weather tickers and summarize the best watchlist candidates"
```

For example, include tickers in the prompt:

```bash
uv run python agent_runner.py --local "Research KXRAINNYC-26MAY31-T0 and KXRAINNYC-26MAY30-T0, then summarize the best watchlist candidates"
```

All recommendations are paper research only. The live MVP uses public Kalshi market data plus public NWS forecasts and does not read private keys or place trades.

