# Docs Index

This folder is the source of truth for the hackathon build.

## Canonical Docs

- `DESIGN.md` - canonical product direction, architecture, conflicts, and build order.
- `TASKS.md` - team coordination, task ownership, and demo checklist.

## Supporting Context

These files are useful background, but are not the canonical implementation source:

- `../DESIGN.md` - teammate's autoresearch/backtesting design.
- `../TASKS.md` - teammate's task split and owner breakdown.
- `../kalshi_strats.md` - strategy catalog and market examples.
- `../hackathon.md` - hackathon logistics, prizes, judging criteria, and resource links.
- `../.cursor/plans/kalshi_weather_agent_92ec1e3f.plan.md` - earlier Cursor implementation plan for a weather-market terminal MVP.

## External References

Vendored third-party material — look it up locally instead of re-fetching the web:

- `references/kalshi/` - curated Kalshi Trade API v2 docs (auth signing, markets, orderbook, orders, fees) + `weather-markets.md` (ticker → settlement station mapping).
- `references/weather/` - NWS (`api.weather.gov`) and Open-Meteo data-source references for forecasts and historical backtesting data.
- `references/modeling/` - probability, edge-after-fees, and scoring (Brier/calibration/Sharpe) reference.
- `references/autoresearch/` - Karpathy's autonomous research loop, cleaned to the methodology and mapped onto our frozen-backtester design.

When plans diverge, update `DESIGN.md` first, then update `TASKS.md`.
