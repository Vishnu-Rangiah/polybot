> Source: https://help.kalshi.com/en/articles/13823837-weather-markets, https://docs.kalshi.com/getting_started/quick_start_market_data, Kalshi public API `https://api.elections.kalshi.com/trade-api/v2/` (series/events/markets endpoints, queried live), contract-terms PDFs under `https://kalshi-public-docs.s3.amazonaws.com/contract_terms/`, NWS Climatological Report product pages on forecast.weather.gov (researched 2026-05-30)

# Kalshi Weather Markets — Resolution & Settlement Reference

This document tells a trading agent how to go from a **Kalshi weather market ticker** to its **exact resolution rule** and **the specific dataset/station that settles it**. The market title (e.g. "Highest temperature in NYC") is *not* sufficient — the settlement source is a single named station/report, and the day boundary has a non-obvious DST quirk.

**Golden rule for the agent:** never infer the settlement source from the city name. Always pull it live from the API (`settlement_sources` on the series, and `rules_primary` on the individual market). These fields are authoritative and confirmed below from live API responses.

---

## 1. Market families (confirmed via live API)

| Family | Example series ticker | Title pattern | Structure |
|---|---|---|---|
| Daily HIGH temperature | `KXHIGHNY`, `KXHIGHLAX`, `KXHIGHCHI` | "Highest temperature in <city>" | One event/day split into many mutually-exclusive temperature buckets |
| Daily LOW temperature | `KXLOWNY`, `KXLOWLAX`, `KXLOWCHI` | "Lowest temperature in <city>" | Same bucket structure as HIGH (seasonal; may have no open events in warm months) |
| Rain / precipitation | `KXRAINNYC`, `KXRAINHOU`, `KXRAINMIA` | "<city> rain" / "Will it rain in <city>?" | Single binary YES/NO market per day (`mutually_exclusive: false`) |
| Snow | `KXSNOWNY` (legacy `SNOWNY`) | "Snow in NYC" / "Total snow in NYC" | Bucketed by snowfall amount (events seen only in winter; no open events on 2026-05-30) |

Notes:
- There is a legacy/duplicate rain series for NYC: `KXRAINNYC` (settles on the **NWS Climatological Report**, Central Park) vs. `KXRAINNY` (settles on a **USGS** water-data gauge). They are different products with different settlement sources — confirm per ticker.
- Kalshi also markets weather more broadly under the hub `kalshi.com/hub/weather`; the API category is `"Climate and Weather"`.

---

## 2. Ticker / series / event / market conventions (confirmed)

Hierarchy: **Series → Event → Market** (each market is one binary YES/NO contract).

- **Series ticker:** `KX` + family + city code. Examples: `KXHIGHNY`, `KXHIGHLAX`, `KXHIGHCHI`, `KXLOWNY`, `KXRAINNYC`. (Older series omit the `KX` prefix, e.g. `SNOWNY`.) City codes are not uniform — NYC is `NY` for temp but `NYC`/`NY` for rain; confirm per family.
- **Event ticker:** `<SERIES>-<YY><MON><DD>`, e.g. `KXHIGHNY-26MAY30` = NYC high temp for 2026-05-30. One event = one calendar day. `mutually_exclusive: true` for temperature events (exactly one bucket pays out).
- **Market ticker (temperature buckets):** `<EVENT>-<TYPE><STRIKE>`:
  - `B<midpoint>` = a bounded *between* bucket. Example `KXHIGHNY-26MAY30-B70.5` → subtitle "70° to 71°", `floor_strike=70`, `cap_strike=71`.
  - `T<strike>` = an open-ended *tail* bucket. `KXHIGHNY-26MAY30-T68` → "67° or below" (`cap_strike=68`, no floor); `KXHIGHNY-26MAY30-T75` → "76° or above" (`floor_strike=75`, no cap).
  - So a high-temp event for a mild day looks like: `≤67°`, `68–69°`, `70–71°`, `72–73°`, `74–75°`, `≥76°` (buckets are 2°F wide, edges adjusted to forecast). Read `floor_strike`/`cap_strike` numerically rather than parsing the subtitle.
- **Market ticker (rain):** single market `<EVENT>-T0`, e.g. `KXRAINNYC-26MAY31-T0`, subtitle "Rain in NYC". Resolves YES if precipitation `> 0` inches (Trace and Record both count as YES — see §3f).

How to list them via the public API:
```
# Series metadata + settlement source(s):
GET https://api.elections.kalshi.com/trade-api/v2/series/KXHIGHNY
# Open events (one per day):
GET https://api.elections.kalshi.com/trade-api/v2/events?series_ticker=KXHIGHNY&status=open
# All bucket markets for a given day (with rules_primary text):
GET https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker=KXHIGHNY-26MAY30
# Or all open markets for a series at once:
GET https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXHIGHNY&status=open
```
(Docs reference the same paths under the `external-api.kalshi.com` and `api.elections.kalshi.com` hosts; the `elections` host responded for all calls used here.)

---

## 3. THE SETTLEMENT SOURCE (the critical section)

### 3a. Where to find it programmatically
Two authoritative fields:
1. **`series.settlement_sources[]`** — a list of `{name, url}`. For temperature/most-rain series this is an NWS **Climatological Report (CLI)** product URL that encodes the exact office and reporting station.
2. **`market.rules_primary`** — verbatim resolution text naming the station and the report. Example (confirmed): *"If the highest temperature recorded in **Central Park, New York** for May 30, 2026 as reported by the **National Weather Service's Climatological Report (Daily)**, is between 68-69°, then the market resolves Yes."*

The series object also carries `contract_terms_url` (a PDF, e.g. `.../contract_terms/NHIGH.pdf`) and `product_metadata.important_info` warning that *only* the NWS Daily Climate Report value settles the market — not AccuWeather/Google/iOS Weather.

### 3b. Decoding the CLI settlement URL → station
The settlement URL form is:
```
https://forecast.weather.gov/product.php?site=<WFO>&product=CLI&issuedby=<STN>
```
- `site=<WFO>` = the NWS forecast office issuing the report (e.g. `OKX` = New York office).
- `issuedby=<STN>` = the **3-letter station** whose climate report settles the market. This is the actual measurement point. **This code is the key the agent needs** to find the matching NWS/Open-Meteo station.

### 3c. Confirmed city → settlement-source mapping (HIGH temperature series)

| City | Series | WFO `site` | `issuedby` station | Measurement point (per rules text / station) |
|---|---|---|---|---|
| New York | `KXHIGHNY` | OKX | `NYC` | **Central Park** (NWS station KNYC / GHCND `USW00094728`) |
| Los Angeles | `KXHIGHLAX` | LOX | `LAX` | LA Intl Airport (KLAX) |
| Chicago | `KXHIGHCHI` | LOT | `MDW` | **Chicago Midway** (KMDW) — *not* O'Hare |
| Miami | `KXHIGHMIA` | MFL | `MIA` | Miami Intl (KMIA) |
| Austin | `KXHIGHAUS` | EWX | `AUS` | Austin-Bergstrom (KAUS) |
| Denver | `KXHIGHDEN` | BOU | `DEN` | Denver Intl (KDEN) |
| Philadelphia | `KXHIGHPHIL` | PHI | `PHL` | Philadelphia Intl (KPHL) |
| Houston | `KXHIGHHOU` | HGX | `HOU` | Houston (KHOU / Hobby area — confirm via report header) |

Stations marked KXXX are the standard ICAO for the `issuedby` code — **confirmed by the CLI URL station code; the explicit station name is only verbatim-confirmed for NYC (Central Park). Treat the airport identity for other cities as high-confidence inference, and verify against the CLI report header or contract PDF before trusting it for settlement-sensitive trades.**

### 3d. Settlement source varies by FAMILY and city — do not assume
Confirmed examples where the source is *not* a city CLI report:
- `KXRAINNYC` → NWS Climatological Report, Central Park (`site=OKX&issuedby=NYC`).
- `KXRAINNY` (separate series) → **USGS** gauge `01376520` (waterdata.usgs.gov).
- `KXRAINHOU` → generic NWS climate page `weather.gov/wrh/Climate?wfo=hgx`.
- `KXRAINMIA` → **AccuWeather** (`https://www.accuweather.com`) — a different data product entirely.
- `KXLOWLAX`, `KXLOWMIA`, `KXLOWCHI`, `KXLOWAUS` → generic "National Weather Service" / `weather.gov/srh/nwsoffices` (less specific than the HIGH series; resolve the exact station from `rules_primary` of the day's market, not the series source).
- `KXLOWNY` → lists generic NWS plus a global-temperature contract PDF; again read the market-level rules.

**Takeaway:** the LOW-temperature and some RAIN series expose a *generic* settlement URL at the series level; the precise station appears in the per-market `rules_primary`. Always fall back to `rules_primary` when the series `settlement_sources` URL is generic.

### 3e. Day boundary, timezone, DST (confirmed from Help Center)
- Settlement uses the **final NWS Daily Climate Report** (CLI), typically issued the **following morning**.
- NWS daily climate reports are tabulated in **local standard time** year-round. Consequence (verbatim): during **Daylight Saving Time the daily high is recorded over 1:00 AM → 12:59 AM local (next day)**, i.e. the "day" is shifted one hour, NOT a clean local-midnight-to-midnight window. The agent must align any forecast/observation window to LST, not local civil time, in summer.
- Settlement may be **delayed** when (a) the high is inconsistent with 6-hr / 24-hr METAR highs, or (b) the final CLI value is lower than a preliminary report. The market value used is the **final** CLI figure; preliminary values may differ due to rounding/conversion.

### 3f. Close/expiration timing & edge cases (confirmed from `rules_secondary`)
- Rain (`KXRAINNYC`): *"This market will close and expire the sooner of the first 10:00 AM ET following the release of data for <date> or <date+7 days>."* If the CLI is inconclusive after 7 days, Kalshi falls back to the "Weather" and "1 Hour Precip (in)" columns of the NWS time series at `https://www.weather.gov/wrh/timeseries?site=knyc` (rule 7.2 of the rulebook).
- Rain YES condition: precipitation **strictly greater than 0 inches**; a report of **T (Trace)** or **R (Record)** also resolves **YES** (`rules_secondary`).

---

## 4. Practical pipeline for the agent: ticker → rule → station to query

1. **Parse the ticker** to identify family + city + date: `KXHIGHNY-26MAY30-B70.5` → series `KXHIGHNY`, event date 2026-05-30, bucket 70–71°F.
2. **Fetch the series** `GET /series/{series_ticker}` → read `settlement_sources[].url`.
3. **Decode the CLI URL**: extract `issuedby=<STN>`. That 3-letter code is the settling station. Map to ICAO `K<STN>` for METAR/Open-Meteo (e.g. `NYC`→Central Park KNYC; `MDW`→KMDW; `LAX`→KLAX). For NYC specifically the point is **Central Park**, not JFK/LGA/EWR.
4. **Fetch the day's markets** `GET /markets?event_ticker={event}` and read each `rules_primary` to confirm the exact measurement point and the bucket math (use `floor_strike`/`cap_strike`, in whole °F, inclusive ranges as written e.g. "68° to 69°").
5. **Query the matching observation/forecast:**
   - NWS: pull the same station's data, ideally the **CLI Daily Climate Report** (`forecast.weather.gov/product.php?site=<WFO>&product=CLI&issuedby=<STN>`) for the realized value; use the **LST day window** (shift +0h in standard time, account for the 1 AM–12:59 AM LST window during DST). See `../weather/nws-api.md`.
   - Open-Meteo: request the station's lat/lon with `temperature_unit=fahrenheit`, daily `temperature_2m_max`/`_min`, and set `timezone` to the city's local zone, then **manually re-window to LST** to match NWS rather than trusting Open-Meteo's civil-day max. See `../weather/open-meteo.md`.
6. **For rain:** condition is precip `> 0"` at the named station; Trace counts as YES. Treat as a single binary, not a bucket set.
7. **Caveats to encode:** NWS rounds/converts (sub-degree noise near a bucket edge matters a lot for 2°F buckets); settlement can lag a day; preliminary ≠ final; some cities (Miami rain) settle on a *non-NWS* source — branch on the actual `settlement_sources` value rather than assuming NWS everywhere.

---

## 5. Cities currently covered (confirmed present in API on 2026-05-30)

- **HIGH temp (`KXHIGH*`):** New York (NY), Los Angeles (LAX), Chicago (CHI), Miami (MIA), Austin (AUS), Denver (DEN), Philadelphia (PHIL), Houston (HOU). *(Likely more exist — these are the codes confirmed responding; probing additional codes such as Boston/DC/Phoenix/Seattle/Dallas/Atlanta did not return series under the guessed tickers, so either they aren't offered or use different city codes — verify by listing series under the "Climate and Weather" category rather than guessing.)*
- **LOW temp (`KXLOW*`):** New York (NY), Los Angeles (LAX), Chicago (CHI), Austin (AUS), Miami (MIA). Seasonal — events may be absent off-season.
- **RAIN:** NYC (`KXRAINNYC` and separate `KXRAINNY`), Houston (`KXRAINHOU`), Miami (`KXRAINMIA`).
- **SNOW:** NYC (`KXSNOWNY` / legacy `SNOWNY`) — winter only.

**Inferred vs confirmed:** all series tickers, titles, settlement-source URLs, bucket/ticker structures, rain YES-condition, close timing, and the NYC=Central Park station are **confirmed** from live API/Help Center text. The exact airport identity for non-NYC stations is **inferred** from the `issuedby` ICAO code and should be re-verified against each city's CLI report header or contract-terms PDF before settlement-critical use. The list of covered cities is a **lower bound** (only probed tickers); enumerate the full set by paging events/series under the `Climate and Weather` category instead of guessing city codes.
