> Source: https://docs.kalshi.com/api-reference/market/get-market-orderbook.md, .../get-multiple-market-orderbooks.md, https://docs.kalshi.com/getting_started/orderbook_responses.md (scraped 2026-05-30)

# Orderbook

## Bids-Only Model (Conceptual)

Kalshi's orderbook returns **only bids** — both YES bids and NO bids — and **never asks**. This works because in a binary market the two sides sum to $1.00, so every order has a complementary opposite:

- A **YES bid** at price X is equivalent to a **NO ask** at ($1.00 − X).
- A **NO bid** at price Y is equivalent to a **YES ask** at ($1.00 − Y).

Publishing only bids therefore conveys the complete book without redundancy.

### Deriving implied asks

```
best YES ask = $1.00 - (highest NO bid)
best NO ask  = $1.00 - (highest YES bid)
```

In cents this is `yes_ask = 100 - best_no_bid` and `no_ask = 100 - best_yes_bid`.

**Example:** If the highest YES bid is `"0.4200"` and the highest NO bid is `"0.5600"`, then:
- best YES ask = 1.00 − 0.5600 = $0.44
- bid-ask spread (YES) = 0.44 − 0.42 = $0.02

### Price-level format

Each price level is a 2-element array `[price, count]`:

- element `[0]` — dollar price as a string, e.g. `"0.4200"` = $0.42.
- element `[1]` — contract quantity as a fixed-point string, e.g. `"13.00"` = 13 contracts.

Levels are sorted **ascending**, so the **last element** of each array is the best (highest) bid for that side.

---

## Get Market Orderbook

`GET /markets/{ticker}/orderbook`

### Path Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `ticker` | string | Yes | Market ticker. |

### Query Parameters

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `depth` | integer | No | 0 | Depth of the orderbook to retrieve. `0` or negative = all levels; `1`–`100` = that many levels. |

### Response

```json
{
  "orderbook_fp": {
    "yes_dollars": [ ["0.1500", "100.00"] ],
    "no_dollars":  [ ["0.1500", "100.00"] ]
  }
}
```

- `orderbook_fp.yes_dollars` — array of `[price_dollars, count_fp]` YES bid levels.
- `orderbook_fp.no_dollars` — array of `[price_dollars, count_fp]` NO bid levels.

**Status codes:** 200, 401 Unauthorized, 404 Not Found, 500.

Error body shape:

```json
{ "code": "string", "message": "string", "details": "string", "service": "string" }
```

---

## Get Multiple Market Orderbooks (bulk)

`GET /markets/orderbooks`

Fetch orderbooks for many markets in one call.

### Query Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `tickers` | array[string] | Yes | List of market tickers. Min 1, max 100 items; each up to 200 characters. |

### Response

```json
{
  "orderbooks": [
    {
      "ticker": "string",
      "orderbook_fp": {
        "yes_dollars": [ ["0.1500", "100.00"] ],
        "no_dollars":  [ ["0.1500", "100.00"] ]
      }
    }
  ]
}
```

**Status codes:** 200, 400 Bad Request, 401 Unauthorized, 500.

> Requires the standard `KALSHI-ACCESS-*` headers when called as an authenticated request; market data is also accessible publicly.
