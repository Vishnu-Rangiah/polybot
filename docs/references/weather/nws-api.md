> Source: https://api.weather.gov, https://www.weather.gov/documentation/services-web-api, https://weather-gov.github.io/api/general-faqs (scraped 2026-05-30)

# NWS API (api.weather.gov) — Forecast Client Reference

A developer reference for the US National Weather Service public REST API, focused on building a forecast/observation client for a Kalshi weather-market trading agent.

## Basics

- **Base URL:** `https://api.weather.gov`
- **Cost:** Free. **No API key, no account, no token.**
- **Transport:** HTTPS only.
- **Coverage:** United States (and territories) only.
- **Times:** All timestamps are ISO-8601 with offset, e.g. `2026-05-30T15:00:00-05:00`.
- **Default format:** GeoJSON (`application/geo+json`). Content negotiation via `Accept` header also supports `application/ld+json` (JSON-LD), DWML, CAP, ATOM. For trading code, the default GeoJSON is fine — read everything under the top-level `properties` object.

## Mandatory User-Agent header

The API **rejects requests without a `User-Agent` header.** This is the single most common reason a client gets blocked.

> "A User Agent is required to identify your application. This string can be anything, and the more unique to your application the less likely it will be affected by a security event."

Recommended format — app name plus a contact so NWS can reach you about security events or abuse:

```
User-Agent: (myweatherapp.com, contact@myweatherapp.com)
```

Use something identifying your app and a real contact email, e.g. `kalshi-weather-bot/1.0 (schmitzandrew03@gmail.com)`.

## Two-step lookup flow

You cannot query a forecast by lat/lon directly. You first resolve a coordinate to a **gridpoint**, then fetch the forecast URL from that response.

### Step 1 — `GET /points/{lat},{lon}`

Example: `GET https://api.weather.gov/points/39.7456,-97.0892`

The `properties` object contains the grid mapping and ready-made forecast URLs:

```json
{
  "properties": {
    "gridId": "TOP",
    "cwa": "TOP",
    "gridX": 32,
    "gridY": 81,
    "forecast": "https://api.weather.gov/gridpoints/TOP/32,81/forecast",
    "forecastHourly": "https://api.weather.gov/gridpoints/TOP/32,81/forecast/hourly",
    "forecastGridData": "https://api.weather.gov/gridpoints/TOP/32,81",
    "observationStations": "https://api.weather.gov/gridpoints/TOP/32,81/stations",
    "relativeLocation": { "properties": { "city": "Linn", "state": "KS" } },
    "timeZone": "America/Chicago",
    "radarStation": "KTWX"
  }
}
```

- `forecast` — 12-hour day/night periods, ~7 days.
- `forecastHourly` — hourly periods, ~7 days. **Use this for trading.**
- `forecastGridData` — raw numerical grid data.
- The office/grid identifiers map to a forecast resolution of about 2.5 km × 2.5 km.

### Step 2 — `GET` the forecastHourly URL

Equivalent to `GET /gridpoints/{office}/{gridX},{gridY}/forecast/hourly`, e.g. `GET https://api.weather.gov/gridpoints/TOP/32,81/forecast/hourly`.

Returns `properties.periods` — an array of hourly period objects.

## Forecast period fields (the trading-relevant ones)

Each element of `properties.periods` from `/forecast/hourly`:

```json
{
  "number": 1,
  "startTime": "2026-05-30T15:00:00-05:00",
  "endTime": "2026-05-30T16:00:00-05:00",
  "isDaytime": true,
  "temperature": 82,
  "temperatureUnit": "F",
  "temperatureTrend": null,
  "probabilityOfPrecipitation": { "unitCode": "wmoUnit:percent", "value": 13 },
  "dewpoint": { "unitCode": "wmoUnit:degC", "value": 21.11111111111111 },
  "relativeHumidity": { "unitCode": "wmoUnit:percent", "value": 67 },
  "windSpeed": "15 mph",
  "windDirection": "SE",
  "shortForecast": "Partly Sunny",
  "detailedForecast": ""
}
```

| Field | Type / shape | Notes for trading |
|---|---|---|
| `startTime` / `endTime` | ISO-8601 string | Each hourly period spans one hour. Match these to the market's settlement window. |
| `isDaytime` | bool | Useful for day-high vs overnight-low markets. |
| `temperature` | number (integer) | In the hourly forecast, temperature is a plain number, **not** a `{unitCode,value}` object. |
| `temperatureUnit` | string | Usually `"F"` for hourly. Always read this — don't assume. |
| `probabilityOfPrecipitation` | `{ unitCode, value }` | `value` is a percent **or `null`**. Treat `null` as "no/0% chance" or "unknown" deliberately — do not let it crash parsing. |
| `dewpoint` | `{ unitCode, value }` | `unitCode` is `wmoUnit:degC` (Celsius) even though temperature is reported in F. Convert as needed. `value` can be a long float. |
| `relativeHumidity` | `{ unitCode, value }` | Percent; `value` may be null. |
| `windSpeed` | **string** with units, e.g. `"15 mph"` or a range `"10 to 15 mph"` | Parse the number(s) out yourself. |
| `windDirection` | string cardinal, e.g. `"SE"` | |
| `shortForecast` | string, e.g. `"Partly Sunny"` | Human-readable category; handy for sanity checks / sky-condition markets. |
| `temperatureTrend` | string or null | e.g. `"falling"`; usually null in hourly. |

Note: the 12-hour `/forecast` endpoint shares this shape but adds a `name` field (`"Tonight"`, `"Saturday"`) and a populated `detailedForecast`.

## Observations (settlement "ground truth")

Forecasts are predictions; for settling/back-testing against what actually happened, use station observations.

### Find stations for a location

`GET /gridpoints/{office}/{gridX},{gridY}/stations` (the `observationStations` URL from the points response). Returns nearby stations ordered roughly by distance. Each entry:

```json
{
  "id": "https://api.weather.gov/stations/KMYZ",
  "stationIdentifier": "KMYZ",
  "name": "Marysville Municipal Airport",
  "geometry": { "type": "Point", "coordinates": [-96.6306, 39.8553] },
  "distance": { "unitCode": "wmoUnit:m", "value": 41130.73 },
  "timeZone": "America/Chicago"
}
```

Pick the station that matches the official Kalshi settlement source (often a specific airport ASOS, e.g. `KNYC`, `KLAX`, `KMDW`). Don't just grab the first one. See `../kalshi/weather-markets.md` for the city → settling-station mapping.

### Latest observation

`GET /stations/{stationId}/observations/latest`, e.g. `GET https://api.weather.gov/stations/KTOP/observations/latest`. Read `properties`:

```json
{
  "timestamp": "2026-05-30T19:45:00+00:00",
  "temperature":        { "unitCode": "wmoUnit:degC", "value": 24,  "qualityControl": "V" },
  "dewpoint":           { "unitCode": "wmoUnit:degC", "value": 21,  "qualityControl": "V" },
  "windSpeed":          { "unitCode": "wmoUnit:km_h-1", "value": 29.628, "qualityControl": "V" },
  "relativeHumidity":   { "unitCode": "wmoUnit:percent", "value": 83.34, "qualityControl": "V" },
  "barometricPressure": { "unitCode": "wmoUnit:Pa", "value": 100982.11, "qualityControl": "V" },
  "precipitationLastHour": { "unitCode": "wmoUnit:mm", "value": null, "qualityControl": "Z" },
  "textDescription": "Clear"
}
```

Observation gotchas:
- **Observed temperature/dewpoint are in Celsius** (`wmoUnit:degC`), wind in km/h — unlike the hourly forecast's Fahrenheit. Convert before comparing to a market.
- Any `value` can be **`null`** (precipitation fields are frequently null when there was none, paired with `qualityControl: "Z"`).
- `qualityControl` codes: `"V"` verified, `"C"` coarse/passed, `"Z"` suspect/unchecked. Prefer verified values for settlement.
- Observations may lag **up to ~20 minutes** behind real time due to upstream (MADIS) QC processing. To get the actual daily high/low for settlement, page the historical observations list (`/stations/{id}/observations?start=...&end=...`) rather than relying on a single `latest` reading.

> Important: Kalshi temperature markets settle on the NWS **Climatological Report (CLI)** daily value, not on raw `/observations` METARs. The CLI is a separate product (`forecast.weather.gov/product.php?site=<WFO>&product=CLI&issuedby=<STN>`). Use `/observations` for live estimation/backtesting; use the CLI for the actual settled number. Details in `../kalshi/weather-markets.md`.

## Caching guidance

The API is explicitly cache-friendly and returns `Cache-Control` (advises how long to hold a response) and `Last-Modified` (for conditional `If-Modified-Since` revalidation) headers. Honor them.

- **`/points/{lat,lon}` is effectively static** per coordinate — cache it long-term (the forecast/grid URLs rarely change). Re-resolve only occasionally: office/grid mappings "may occasionally change," so re-check periodically (e.g. daily/weekly), not every request.
- **Forecasts update roughly hourly** — caching a forecast response for ~10–60 minutes is reasonable.
- **Observations** update as stations report (about hourly, sometimes more often).
- Do **not** use cache-busting (random query-string params); it defeats the cache and raises your chance of being throttled.

## Rate limits / throttling

- NWS does not publish exact numbers — there are "reasonable rate limits in place to prevent abuse."
- When exceeded, a request **returns an error and may be retried after the limit clears — typically within ~5 seconds.** Some documentation/community reports describe the throttle response as HTTP **429**; in practice NWS has also been observed returning **403** with a Reference ID in the body for rate/security blocks. Treat **both 429 and 403** as "back off and retry."
- **Requests directly from clients are rarely limited; shared proxies/IPs are far more likely to hit the limit.**
- Practical client policy: serialize or gently throttle requests, cache aggressively (above), and on 429/403/5xx retry with exponential backoff (e.g. start ~5s).

## Common gotchas

- **HTTPS only** — plain HTTP will not work.
- **Round/truncate lat,lon to ≤ 4 decimal places.** "The API doesn't support more than four decimal places of precision in coordinates" (~10 m). Passing more decimals can cause redirects or errors — format coordinates yourself before building the URL.
- **`probabilityOfPrecipitation.value` is often `null`** — handle it explicitly; don't assume a number.
- **Unit mismatch:** hourly forecast `temperature` is Fahrenheit (per `temperatureUnit`), but `dewpoint` and all observation values are metric (degC, km/h, Pa, mm). Always read `unitCode` / `temperatureUnit`.
- **`windSpeed` in forecasts is a string** ("15 mph" or "10 to 15 mph") — parse it; in observations it's a numeric `{unitCode,value}`.
- **Gridpoint/forecast endpoints occasionally return 500** (transient server-side). Retry with backoff; a second attempt usually succeeds.
- The `/forecast` and `/forecast/hourly` endpoints **drop periods already in the past** — the first period in the array is the current hour/period, not midnight.
- Provide a stable, identifying `User-Agent` with contact info so you can be notified during security events rather than silently blocked.

## Python example: points → hourly flow

```python
import requests

# Identify your app + a real contact. Without this header, NWS rejects the request.
HEADERS = {
    "User-Agent": "kalshi-weather-bot/1.0 (schmitzandrew03@gmail.com)",
    "Accept": "application/geo+json",
}
BASE = "https://api.weather.gov"


def get_hourly_forecast(lat: float, lon: float):
    # Step 1: resolve coordinate -> gridpoint. Round to <=4 decimals.
    pts = requests.get(
        f"{BASE}/points/{lat:.4f},{lon:.4f}",
        headers=HEADERS,
        timeout=30,
    )
    pts.raise_for_status()
    props = pts.json()["properties"]

    hourly_url = props["forecastHourly"]   # cache props; it's static per coordinate

    # Step 2: fetch the hourly forecast (retry once on transient 5xx).
    for attempt in range(3):
        r = requests.get(hourly_url, headers=HEADERS, timeout=30)
        if r.status_code in (429, 403) or r.status_code >= 500:
            import time
            time.sleep(5 * (attempt + 1))   # back off and retry
            continue
        r.raise_for_status()
        return r.json()["properties"]["periods"]
    r.raise_for_status()


periods = get_hourly_forecast(39.7456, -97.0892)
for p in periods[:6]:
    pop = p["probabilityOfPrecipitation"]["value"]   # may be None
    print(
        p["startTime"],
        f'{p["temperature"]}{p["temperatureUnit"]}',
        f'POP={pop if pop is not None else "n/a"}%',
        p["shortForecast"],
    )
```

## Endpoint cheat sheet

| Endpoint | Purpose |
|---|---|
| `GET /points/{lat},{lon}` | Resolve coordinate → office/grid + forecast & station URLs (cache this) |
| `GET /gridpoints/{office}/{gridX},{gridY}/forecast/hourly` | Hourly forecast (temp, POP, dewpoint, wind) |
| `GET /gridpoints/{office}/{gridX},{gridY}/forecast` | 12-hour day/night forecast |
| `GET /gridpoints/{office}/{gridX},{gridY}` | Raw `forecastGridData` |
| `GET /gridpoints/{office}/{gridX},{gridY}/stations` | Observation stations near the grid |
| `GET /stations/{stationId}/observations/latest` | Latest observation (settlement ground truth) |
| `GET /stations/{stationId}/observations?start=&end=` | Historical observations (daily high/low) |

Full machine-readable spec: `https://api.weather.gov/openapi.json`. General docs: `https://www.weather.gov/documentation/services-web-api` and `https://weather-gov.github.io/api/`.
