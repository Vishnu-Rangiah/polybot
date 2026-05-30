> Source: https://docs.kalshi.com/api-reference/market/get-markets.md, .../get-market.md, https://docs.kalshi.com/api-reference/events/get-event.md, https://docs.kalshi.com/api-reference/market/get-series.md (scraped 2026-05-30)

# Markets, Events, and Series

All paths are relative to a base URL such as `https://external-api.kalshi.com/trade-api/v2`. Market-data endpoints are publicly accessible (no auth required).

---

## Get Markets

`GET /markets`

Returns a paginated list of markets, with filtering.

### Query Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `limit` | integer | No | Results per page. Default 100, max 1000. |
| `cursor` | string | No | Pagination cursor from a previous response. |
| `event_ticker` | string | No | Filter by event ticker. Only a single event ticker is supported. |
| `series_ticker` | string | No | Filter by series ticker. |
| `min_created_ts` | integer | No | Filter items created after this Unix timestamp. |
| `max_created_ts` | integer | No | Filter items created before this Unix timestamp. |
| `min_updated_ts` | integer | No | Return markets with metadata updated later than this Unix timestamp. Tracks non-trading changes only. |
| `min_close_ts` | integer | No | Filter items that close after this Unix timestamp. |
| `max_close_ts` | integer | No | Filter items that close before this Unix timestamp. |
| `min_settled_ts` | integer | No | Filter items that settled after this Unix timestamp. |
| `max_settled_ts` | integer | No | Filter items that settled before this Unix timestamp. |
| `status` | string | No | Filter by status: `unopened`, `open`, `paused`, `closed`, `settled`. |
| `tickers` | string | No | Comma-separated list of market tickers to retrieve. |
| `mve_filter` | string | No | `only` (multivariate events only) or `exclude` (exclude multivariate events). |

### Response: `GetMarketsResponse`

```json
{
  "markets": [ /* array of Market objects (see schema below) */ ],
  "cursor": "string"
}
```

### Market object schema

```json
{
  "ticker": "string",
  "event_ticker": "string",
  "market_type": "binary|scalar",
  "yes_sub_title": "string",
  "no_sub_title": "string",
  "created_time": "2024-01-01T00:00:00Z",
  "updated_time": "2024-01-01T00:00:00Z",
  "open_time": "2024-01-01T00:00:00Z",
  "close_time": "2024-01-01T00:00:00Z",
  "expected_expiration_time": "2024-01-01T00:00:00Z",
  "latest_expiration_time": "2024-01-01T00:00:00Z",
  "settlement_timer_seconds": 0,
  "status": "initialized|inactive|active|closed|determined|disputed|amended|finalized",
  "yes_bid_dollars": "0.5600",
  "yes_bid_size_fp": "10.00",
  "yes_ask_dollars": "0.5600",
  "yes_ask_size_fp": "10.00",
  "no_bid_dollars": "0.5600",
  "no_ask_dollars": "0.5600",
  "last_price_dollars": "0.5600",
  "volume_fp": "10.00",
  "volume_24h_fp": "10.00",
  "open_interest_fp": "10.00",
  "notional_value_dollars": "0.5600",
  "previous_yes_bid_dollars": "0.5600",
  "previous_yes_ask_dollars": "0.5600",
  "previous_price_dollars": "0.5600",
  "liquidity_dollars": "0.5600",
  "settlement_value_dollars": "0.5600",
  "settlement_ts": "2024-01-01T00:00:00Z",
  "expiration_value": "string",
  "occurrence_datetime": "2024-01-01T00:00:00Z",
  "result": "yes|no|scalar|",
  "can_close_early": true,
  "fractional_trading_enabled": true,
  "fee_waiver_expiration_time": "2024-01-01T00:00:00Z",
  "early_close_condition": "string",
  "strike_type": "greater|greater_or_equal|less|less_or_equal|between|functional|custom|structured",
  "floor_strike": 0.0,
  "cap_strike": 0.0,
  "functional_strike": "string",
  "custom_strike": {},
  "rules_primary": "string",
  "rules_secondary": "string",
  "mve_collection_ticker": "string",
  "mve_selected_legs": [
    { "event_ticker": "string", "market_ticker": "string", "side": "string", "yes_settlement_value_dollars": "0.5600" }
  ],
  "primary_participant_key": "string",
  "price_level_structure": "string",
  "price_ranges": [ { "start": "0.5600", "end": "0.5600", "step": "0.5600" } ],
  "is_provisional": true,
  "exchange_index": 0
}
```

### Market field descriptions

- `ticker` — Market identifier.
- `event_ticker` — Associated event identifier.
- `market_type` — `binary` or `scalar`.
- `yes_sub_title` / `no_sub_title` — Shortened title for the yes / no side of this market.
- `created_time` — Market creation timestamp.
- `updated_time` — Time of the last non-trading metadata update.
- `open_time` / `close_time` — Market opening / closing time.
- `expected_expiration_time` — Time when this market is expected to expire.
- `latest_expiration_time` — Latest possible time for this market to expire.
- `settlement_timer_seconds` — Amount of time after determination that the market settles.
- `status` — Current market lifecycle stage.
- `yes_bid_dollars` — Price for the highest YES buy offer, in dollars.
- `yes_bid_size_fp` — Total contract size of orders to buy YES at the best bid price.
- `yes_ask_dollars` — Price for the lowest YES sell offer, in dollars.
- `yes_ask_size_fp` — Total contract size of orders to sell YES at the best ask price.
- `no_bid_dollars` — Price for the highest NO buy offer, in dollars.
- `no_ask_dollars` — Price for the lowest NO sell offer, in dollars.
- `last_price_dollars` — Price for the last traded YES contract, in dollars.
- `volume_fp` — Market volume in contracts (string).
- `volume_24h_fp` — 24h market volume in contracts (string).
- `open_interest_fp` — Number of contracts bought on this market, disregarding netting.
- `notional_value_dollars` — Total value of a single contract at settlement, in dollars.
- `previous_yes_bid_dollars` / `previous_yes_ask_dollars` / `previous_price_dollars` — Prior day's highest YES bid / lowest YES ask / last traded price.
- `liquidity_dollars` — Deprecated; returns `"0.0000"`.
- `settlement_value_dollars` — Settlement value of the YES/LONG side, in dollars. Only filled after determination.
- `settlement_ts` — Timestamp when the market was settled. Only for settled markets.
- `expiration_value` — The value considered for settlement.
- `occurrence_datetime` — Recorded datetime when the underlying event occurred, if available.
- `result` — `yes`, `no`, `scalar`, or `""` (Get Market only).
- `can_close_early` — Whether early closure is possible.
- `fractional_trading_enabled` — Deprecated; always `true`.
- `fee_waiver_expiration_time` — When the market's fee waiver expires.
- `early_close_condition` — Condition under which the market can close early.
- `strike_type` — Defines how the market strike is defined and evaluated.
- `floor_strike` — Minimum expiration value leading to YES settlement.
- `cap_strike` — Maximum expiration value leading to YES settlement.
- `functional_strike` — Mapping from expiration values to settlement values.
- `custom_strike` — Expiration value per target leading to YES settlement.
- `rules_primary` / `rules_secondary` — Plain-language description of the most important / secondary market terms.
- `mve_collection_ticker` — Ticker of the multivariate event collection.
- `mve_selected_legs` — Selected legs in multivariate events (`event_ticker`, `market_ticker`, `side`, `yes_settlement_value_dollars`).
- `primary_participant_key` — Participant identifier.
- `price_level_structure` — Price-level structure (price ranges and tick sizes).
- `price_ranges` — Valid price ranges for orders: `start`, `end`, `step` (tick size) in dollars.
- `is_provisional` — If true, the market may be removed after determination if there is no activity.
- `exchange_index` — Exchange shard identifier; defaults to 0.

**Status codes:** 200 OK, 400 Bad Request, 401 Unauthorized, 500 Internal Server Error.

---

## Get Market

`GET /markets/{ticker}`

### Path Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `ticker` | string | Yes | Market ticker. |

### Response

```json
{ "market": { /* single Market object, same schema as above (includes "result") */ } }
```

**Status codes:** 200, 401 Unauthorized, 404 Not Found, 500.

---

## Get Event

`GET /events/{event_ticker}`

### Path Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `event_ticker` | string | Yes | Event ticker. |

### Query Parameters

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `with_nested_markets` | boolean | No | false | If true, markets are included within the event object. If false, markets are returned as a separate top-level field. |

### Response: `GetEventResponse`

| Field | Type | Description |
|---|---|---|
| `event` | EventData | Data for the event. |
| `markets` | array[Market] | Markets in this event. **Deprecated** in favour of the `markets` field inside the event. |

#### EventData

| Field | Type | Required | Description |
|---|---|---|---|
| `event_ticker` | string | Yes | Unique identifier for this event. |
| `series_ticker` | string | Yes | Unique identifier for the series this event belongs to. |
| `sub_title` | string | Yes | Shortened descriptive title for the event. |
| `title` | string | Yes | Full title of the event. |
| `collateral_return_type` | string | Yes | How collateral is returned when markets settle (e.g. `binary`). |
| `mutually_exclusive` | boolean | Yes | If true, only one market in this event can resolve to `yes`. |
| `available_on_brokers` | boolean | Yes | Whether this event is available to trade on brokers. |
| `category` | string | No | Event category (deprecated). |
| `strike_date` | date-time | No | The specific date this event is based on. Only filled when the event uses a date strike. |
| `strike_period` | string | No | The time period this event covers (e.g. `week`, `month`). |
| `markets` | array[Market] | No | Markets associated with this event. Only populated when `with_nested_markets=true`. |
| `product_metadata` | object | No | Additional metadata for the event. |
| `last_updated_ts` | date-time | No | When this event's metadata was last updated. |
| `fee_type_override` | string | No | Fee-type override; takes precedence over the series-level fee. |
| `fee_multiplier_override` | number | No | Fee multiplier override for this event. |
| `exchange_index` | integer | No | Exchange shard identifier; defaults to 0. |

**Status codes:** 200, 400, 401, 404 Not Found, 500.

> Related: `GET /events` (list events, supports `limit`, `cursor`, `status`, `series_ticker`, `with_nested_markets`).

---

## Get Series

`GET /series/{series_ticker}`

### Path Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `series_ticker` | string | Yes | The ticker of the series to retrieve. |

### Query Parameters

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `include_volume` | boolean | No | false | If true, includes total volume traded across all events in this series. |

### Response

```json
{
  "series": {
    "ticker": "string",
    "frequency": "string",
    "title": "string",
    "category": "string",
    "tags": ["string"],
    "settlement_sources": [ { "name": "string", "url": "string" } ],
    "contract_url": "string",
    "contract_terms_url": "string",
    "product_metadata": {},
    "fee_type": "quadratic|quadratic_with_maker_fees|flat",
    "fee_multiplier": 0,
    "additional_prohibitions": ["string"],
    "volume_fp": "string",
    "last_updated_ts": "2024-01-01T00:00:00Z"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `ticker` | string | Identifier for the series. |
| `frequency` | string | Human-readable frequency (e.g. weekly, daily). |
| `title` | string | Title describing the series. |
| `category` | string | Category this series belongs to. |
| `tags` | array | Subjects this series relates to. |
| `settlement_sources` | array | Official sources used for determination of markets (`name`, `url`). |
| `contract_url` | string | Link to original contract filing. |
| `contract_terms_url` | string | URL to current contract terms. |
| `product_metadata` | object | Internal product metadata. |
| `fee_type` | string | Fee structure type: `quadratic`, `quadratic_with_maker_fees`, or `flat`. |
| `fee_multiplier` | number | Multiplier applied to fee calculations. |
| `additional_prohibitions` | array | Additional trading restrictions. |
| `volume_fp` | string | Total contracts traded across all events (only when `include_volume=true`). |
| `last_updated_ts` | date-time | Timestamp of last metadata update. |

> Related: `GET /series` / `GET /series/list` (Get Series List) returns multiple series, filterable by category.
