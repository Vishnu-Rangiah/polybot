> Source: https://docs.kalshi.com/api-reference/market/get-trades.md, .../get-market-candlesticks.md (scraped 2026-05-30)

# Trades and Candlesticks

## Get Trades

`GET /markets/trades`

Returns a paginated list of public trades (executions) across markets, with optional filtering by market.

### Query Parameters

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `limit` | integer | No | 100 | Results per page (1–1000). |
| `cursor` | string | No | — | Pagination cursor from previous response. |
| `ticker` | string | No | — | Filter by market ticker. |
| `min_ts` | integer | No | — | Filter items after this Unix timestamp. |
| `max_ts` | integer | No | — | Filter items before this Unix timestamp. |

### Response

```json
{
  "trades": [
    {
      "trade_id": "string",
      "ticker": "string",
      "count_fp": "10.00",
      "yes_price_dollars": "0.5600",
      "no_price_dollars": "0.4400",
      "taker_side": "yes",
      "taker_outcome_side": "yes",
      "taker_book_side": "bid",
      "created_time": "2024-01-15T10:30:00Z"
    }
  ],
  "cursor": "string"
}
```

| Field | Description |
|---|---|
| `trade_id` | Unique transaction identifier. |
| `ticker` | Market identifier. |
| `count_fp` | Number of contracts bought or sold (fixed-point string). |
| `yes_price_dollars` / `no_price_dollars` | Trade prices in fixed-point dollars (sum to $1.00). |
| `taker_side` / `taker_outcome_side` | The outcome side (`yes`/`no`) the taker is positioned for. |
| `taker_book_side` | Book-vocabulary equivalent (`bid`/`ask`). |
| `created_time` | Execution timestamp (ISO 8601). |

---

## Get Market Candlesticks

`GET /series/{series_ticker}/markets/{ticker}/candlesticks`

Returns OHLC candlesticks for a single market over a time range.

### Path Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `series_ticker` | string | Yes | Series ticker of the market. |
| `ticker` | string | Yes | Market ticker. |

### Query Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `start_ts` | integer (int64) | Yes | Start Unix timestamp. Candlesticks ending on or after this time are included. |
| `end_ts` | integer (int64) | Yes | End Unix timestamp. Candlesticks ending on or before this time are included. |
| `period_interval` | integer | Yes | Candle period in minutes. Valid values: `1`, `60`, `1440` (1 minute, 1 hour, 1 day). |
| `include_latest_before_start` | boolean | No | Default false. When true, prepends a synthetic candlestick projected to the first period boundary. |

### Response: `GetMarketCandlesticksResponse`

```json
{
  "ticker": "string",
  "candlesticks": [
    {
      "end_period_ts": 1234567890,
      "yes_bid": {
        "open_dollars": "0.5600", "low_dollars": "0.5500",
        "high_dollars": "0.5700", "close_dollars": "0.5650"
      },
      "yes_ask": {
        "open_dollars": "0.5700", "low_dollars": "0.5600",
        "high_dollars": "0.5800", "close_dollars": "0.5750"
      },
      "price": {
        "open_dollars": "0.5650", "low_dollars": "0.5600",
        "high_dollars": "0.5700", "close_dollars": "0.5675",
        "mean_dollars": "0.5663", "previous_dollars": "0.5640"
      },
      "volume_fp": "150.50",
      "open_interest_fp": "2000.00"
    }
  ]
}
```

| Field | Description |
|---|---|
| `end_period_ts` | Unix timestamp marking the end of the candle period. |
| `yes_bid` | OHLC of the YES bid over the period (`open/low/high/close_dollars`). |
| `yes_ask` | OHLC of the YES ask over the period. |
| `price` | OHLC of the traded price, plus `mean_dollars` and `previous_dollars`. |
| `volume_fp` | Contracts traded during the period (fixed-point string). |
| `open_interest_fp` | Open interest at period end (fixed-point string). |

> Related endpoints: `GET /series/{series_ticker}/markets/{ticker}/candlesticks` batch variant (`batch-get-market-candlesticks`), event candlesticks (`/events/{event_ticker}/candlesticks`), and historical candlesticks under `/api-reference/historical/`.
