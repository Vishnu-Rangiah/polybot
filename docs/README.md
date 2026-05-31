# Docs Index

This folder is the source of truth for the current Polybot build.

## Canonical Docs

- `CODE_LAYOUT.md` - package map, Kalshi API modules, and `polybot` CLI commands.
- `DESIGN.md` - canonical product direction, architecture, conflicts, and build order.
- `WEATHER_RESEARCH_MVP.md` - live weather-market research walkthrough for `kalshi_agent.research`.
- `STRATEGY_AUTORESEARCH.md` - operational guide for the `kalshi_agent.autoresearch` Codex/Modal loop.
- `ONE_REAL_AUTORESEARCH_ITERATION.md` - focused walkthrough for one Codex-in-Modal loop attempt and the files it reads.
- `MODAL_SANDBOX_WALKTHROUGH.md` - step-by-step Modal sandbox spin-up (Codex + [polybot/main](https://modal.com/apps/polybot/main)).
- `WEATHER_HYPOTHESES.md` and `WEATHER_HYPOTHESES_TESTABILITY.md` - weather strategy hypotheses and how to evaluate them with the resolved-market backtester.
- `CREDENTIALS.md` - Kalshi API keys (demo + prod, both read-write), how to switch envs, and the ⚠️ real-money warning. Private keys live outside the repo; never commit them.

## Supporting Context

These files are useful background, but are not the canonical implementation source:

- `../.cursor/plans/kalshi_weather_agent_92ec1e3f.plan.md` - earlier Cursor implementation plan for a weather-market terminal MVP.

## External References

Vendored third-party material — look it up locally instead of re-fetching the web:

- `references/kalshi/` - curated Kalshi Trade API v2 docs (auth signing, markets, orderbook, orders, fees) + `weather-markets.md` (ticker → settlement station mapping).
- `references/weather/` - NWS (`api.weather.gov`) and Open-Meteo data-source references for forecasts and historical backtesting data.
- `references/modeling/` - probability, edge-after-fees, and scoring (Brier/calibration/Sharpe) reference.
- `references/autoresearch/` - Karpathy's autonomous research loop, cleaned to the methodology and mapped onto our frozen-backtester design.

When plans diverge, update `DESIGN.md` first, then the implementation walkthroughs.
