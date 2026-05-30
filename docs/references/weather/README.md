# Weather Data — Reference

The data sources the Phase-1 weather agent runs on. The pipeline is
`Kalshi market → settling station → forecast/obs → probability`, so read
`../kalshi/weather-markets.md` first to learn *which* station a market settles on,
then come here for *how* to query it.

| File | Source | Use |
|---|---|---|
| `nws-api.md` | `api.weather.gov` (free, no key) | Live forecasts + observations; the Phase-1 demo's primary source |
| `open-meteo.md` | `open-meteo.com` (free, no key) | **Historical archive** for backtesting (1940+) and a live cross-check vs NWS |

## The one rule that ties these together

Kalshi settles temperature markets on the **NWS Climatological Report (CLI)** value
for a specific named station, in **local standard time** (even in summer). Neither a
raw NWS `/observations` METAR nor an Open-Meteo ERA5 grid cell is guaranteed to equal
that number. So:

- Use these APIs to **model and backtest** (build distributions, estimate edge).
- Verify the **actual settled outcome** against the CLI / official source named in the
  market's `rules_primary` before trusting a fill or a backtest label.

See `../modeling/probability-and-scoring.md` for turning a forecast into a tradeable
probability, and the "wrong source" pitfall.
