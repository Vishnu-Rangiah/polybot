> Source: https://open-meteo.com/en/docs, https://open-meteo.com/en/docs/historical-weather-api, https://open-meteo.com/en/pricing (scraped 2026-05-30)

# Open-Meteo API Reference (for Kalshi Weather-Market Trading)

Open-Meteo provides free weather APIs. Three endpoints matter for a Kalshi weather-market agent:

1. **Historical Forecast API** (`historical-forecast-api.open-meteo.com`) — an archive of *past forecasts* (what the model predicted, as it predicted it) back to ~2021, same schema as the live forecast. **This is the no-lookahead feature source for backtesting** — it answers "what did the forecast say at decision time `t`," which is what a strategy could actually have seen. Used by `kalshi_agent/weather.py` (`MeteoSource`, `as_of_date` set).
2. **Forecast API** (`api.open-meteo.com`) — live forecasts up to 16 days out. The live-demo feature source (`MeteoSource`, `as_of_date=None`) and a cross-check vs NWS.
3. **Historical Weather Archive API** (`archive-api.open-meteo.com`) — ERA5 reanalysis (actual observed weather) back to **1940**, no API key. This is **ground truth, not a forecast** — use it only to *approximate* settlement, never as a backtest feature (feeding the realized outcome to a strategy is lookahead). The real settlement number is Kalshi's cited NWS station; see `../kalshi/weather-markets.md`.

> **Feature vs. settlement — do not mix these up.** Backtest *features* (what the agent sees at `t`) come from the **Historical Forecast** archive. Backtest *ground truth* (did it rain / the high temp) comes from the **station Kalshi settles on**, approximated by ERA5 only as a fallback. Using ERA5 for features silently leaks the answer.
>
> **Coverage caveat:** `precipitation_probability` is only archived in the Historical Forecast feed from ~**late 2024** onward (verified: 2024-12-01 returns values; 2024-09-01 is all-null). Earlier dates yield no signal — `MeteoSource` emits `fair_prob_yes=None` there so the strategy abstains rather than trading on a fabricated 0.5. Scope rain-probability backtests to late-2024+, or fall back to a `precipitation`-amount proxy (available far back) for older windows.

## Access & Licensing

- **Free for non-commercial use. No API key required.** No signup.
- No uptime guarantee on the free shared servers. Commercial use requires an API key and the `customer-` URL prefix (see [pricing](https://open-meteo.com/en/pricing)).
- Base hosts:
  - Forecast: `https://api.open-meteo.com/v1/forecast`
  - Historical archive (ERA5): `https://archive-api.open-meteo.com/v1/archive`
- Response formats: JSON (default), CSV, XLSX. Errors return HTTP 400 with `{"error": true, "reason": "..."}`.

## Free-Tier Rate Limits

| Window | Limit |
|--------|-------|
| Per minute | 600 calls |
| Per hour | 5,000 calls |
| Per day | 10,000 calls |

A single request covering a **wide date range counts as one call** (and one request may pull multiple comma-separated coordinates). For backtesting, pull long ranges per request rather than looping day-by-day — far fewer calls. (There is also a soft per-call cap on the number of daily/hourly cells; very large multi-year + many-variable + many-location requests may need to be split.)

> These exact numbers come from the Open-Meteo author's public statements, not the docs HTML (which lists none). Treat as approximate and back off on HTTP 429.

---

## Historical Weather Archive API

**Endpoint:** `https://archive-api.open-meteo.com/v1/archive`

This is the primary tool for backtesting. It serves **ERA5 reanalysis** — a physically consistent gridded reconstruction of past weather.

### Request Parameters

| Parameter | Required | Default | Notes |
|-----------|----------|---------|-------|
| `latitude` | Yes | — | WGS84. Comma-separate for multiple locations. |
| `longitude` | Yes | — | WGS84. Comma-separate for multiple locations. |
| `start_date` | Yes | — | `YYYY-MM-DD` (ISO8601). |
| `end_date` | Yes | — | `YYYY-MM-DD` (ISO8601). |
| `hourly` | No | — | Comma-separated variable list (see below). |
| `daily` | No | — | Comma-separated variable list. **Requires `timezone`.** |
| `timezone` | No | `GMT` | IANA name (e.g. `America/New_York`) or `auto`. Critical for matching a market's local calendar day. |
| `temperature_unit` | No | `celsius` | Set to `fahrenheit` for US markets. |
| `precipitation_unit` | No | `mm` | Set to `inch` for US markets. |
| `wind_speed_unit` | No | `kmh` | `ms`, `mph`, or `kn`. |
| `timeformat` | No | `iso8601` | Or `unixtime` (GMT+0). |
| `elevation` | No | 90 m DEM | Override grid-cell elevation downscaling. |
| `cell_selection` | No | `land` | `sea` or `nearest`. |

> **Timezone tip:** Kalshi temperature/precip markets settle on the *local* calendar day at the official station. Always pass the station's `timezone` (e.g. `America/New_York`) so the daily aggregations and hourly timestamps align to the same day boundary the market uses. Note Kalshi's DST quirk (the climate "day" runs in local *standard* time year-round) — see `../kalshi/weather-markets.md` §3e; you may need to re-window hourly data to LST yourself.

### Coverage & Latency

- **Earliest data: 1940** (ERA5 global, ~0.25° / ~25 km grid). ERA5-Land (~0.1° / ~11 km) goes back to 1950.
- **~5-day delay** for the most recent dates (ERA5 final). You cannot pull *yesterday's* archive value; for the last few days use the Forecast API with `past_days` instead.

| Source | Region | Resolution | Range | Update lag |
|--------|--------|-----------|-------|-----------|
| ERA5 | Global | ~25 km | 1940–present | ~5 days |
| ERA5-Land | Global | ~11 km | 1950–present | ~5 days |
| CERRA | Europe only | ~5 km | 1985–Jun 2021 | none (frozen) |

### Most Trading-Relevant Variables

**Hourly** (each value is the preceding-hour sum for accumulations):

| Variable | Default unit | US unit option |
|----------|-------------|----------------|
| `temperature_2m` | °C | °F via `temperature_unit=fahrenheit` |
| `relative_humidity_2m` | % | — |
| `dew_point_2m` | °C | °F |
| `precipitation` (rain + showers + snow) | mm | inch via `precipitation_unit=inch` |
| `rain` | mm | inch |
| `wind_speed_10m` | km/h | mph via `wind_speed_unit=mph` |
| `apparent_temperature` | °C | °F |

**Daily** (requires `timezone`):

| Variable | Default unit | US unit option |
|----------|-------------|----------------|
| `temperature_2m_max` | °C | °F |
| `temperature_2m_min` | °C | °F |
| `precipitation_sum` | mm | inch |
| `rain_sum` | mm | inch |
| `wind_speed_10m_max` | km/h | mph |
| `weather_code` | WMO code | — |

> **Note:** `precipitation_probability` does **not** exist in the historical archive — it is a forecast-only variable. In the archive you have the actual realized `precipitation` / `precipitation_sum`, which is exactly what you want for backtesting a "will it rain" market against ground truth.

### JSON Response Shape

The response uses **parallel arrays**: `hourly.time[i]` corresponds to `hourly.temperature_2m[i]` (and every other requested variable at the same index). Daily works the same way.

```json
{
  "latitude": 40.71,
  "longitude": -74.0,
  "elevation": 51.0,
  "generationtime_ms": 2.2,
  "utc_offset_seconds": -14400,
  "timezone": "America/New_York",
  "timezone_abbreviation": "EDT",
  "hourly_units": { "time": "iso8601", "temperature_2m": "°F" },
  "hourly": {
    "time":           ["2024-07-01T00:00", "2024-07-01T01:00", "..."],
    "temperature_2m": [72.1,                71.6,               null]
  },
  "daily_units": { "time": "iso8601", "temperature_2m_max": "°F" },
  "daily": {
    "time":               ["2024-07-01", "2024-07-02"],
    "temperature_2m_max": [88.3,         91.0]
  }
}
```

Multiple coordinates return a JSON list of these objects; CSV/XLSX add a `location_id` column.

### Python Example — Historical Hourly Temperature Series

```python
import requests

# NYC (Central Park ~ KNYC), one date range, hourly temperature in Fahrenheit
params = {
    "latitude": 40.7790,
    "longitude": -73.9692,
    "start_date": "2024-07-01",
    "end_date": "2024-07-31",
    "hourly": "temperature_2m,precipitation,relative_humidity_2m",
    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
    "timezone": "America/New_York",
    "temperature_unit": "fahrenheit",
    "precipitation_unit": "inch",
    "wind_speed_unit": "mph",
}

r = requests.get("https://archive-api.open-meteo.com/v1/archive",
                 params=params, timeout=30)
r.raise_for_status()
data = r.json()

times = data["hourly"]["time"]
temps = data["hourly"]["temperature_2m"]
for t, temp in zip(times[:5], temps[:5]):
    print(t, temp, data["hourly_units"]["temperature_2m"])

# Daily highs (what a "high temp" market settles on)
for d, hi in zip(data["daily"]["time"], data["daily"]["temperature_2m_max"]):
    print(d, "high:", hi)
```

---

## Forecast API (Live Cross-Check vs NWS)

**Endpoint:** `https://api.open-meteo.com/v1/forecast`

Same parameter conventions and response shape as the archive (parallel `time[]` / variable arrays, `hourly`/`daily`/`current` blocks, same unit params).

### Forecast-Specific Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `forecast_days` | 7 | 0–16. |
| `past_days` | 0 | 0–92. Bridges the archive's ~5-day gap for recent days. |
| `current` | — | Comma-separated list for latest observed/now values. |
| `hourly` / `daily` | — | Same variable names as the archive. |
| `models` | `auto` | Best-match blend by default; can pin a specific model. |

The forecast API exposes **`precipitation_probability`** (% chance of >0.1 mm) — useful as a probabilistic signal to compare against NWS PoP and against the market's implied probability.

```python
import requests

params = {
    "latitude": 40.7790, "longitude": -73.9692,
    "hourly": "temperature_2m,precipitation_probability,precipitation,wind_speed_10m",
    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
    "current": "temperature_2m,precipitation",
    "forecast_days": 7,
    "timezone": "America/New_York",
    "temperature_unit": "fahrenheit",
    "precipitation_unit": "inch",
    "wind_speed_unit": "mph",
}
fc = requests.get("https://api.open-meteo.com/v1/forecast",
                  params=params, timeout=30).json()
print(fc["current"])                       # latest snapshot
print(fc["daily"]["temperature_2m_max"])   # forecast daily highs
```

---

## Caveats for Settlement (Read Before Trading)

- **ERA5 is reanalysis on a ~9–25 km grid, not a station observation.** Open-Meteo statistically downscales to your lat/lon, but the value can differ — sometimes by several degrees or a meaningful fraction of an inch — from the **specific official station** that settles a Kalshi market.
- **Kalshi settles on official station observations** (e.g. NWS/ASOS daily climate reports, often from a single named station like KNYC/Central Park or LaGuardia), **not on ERA5 reanalysis.** Grid reanalysis ≠ the settlement number.
- **Use Open-Meteo for modeling and backtesting** — building distributions, calibrating edge, estimating typical bias vs. a station. For the **actual resolved outcome**, verify against the official source the market names (NWS Climate / CLI products, ACIS/xmACIS, or the station's daily summary). See `../kalshi/weather-markets.md`.
- The **~5-day archive lag** means you cannot use the archive to confirm a market that just settled; bridge with the Forecast API `past_days` or go straight to the official obs.
