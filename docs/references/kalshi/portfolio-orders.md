> Source: https://docs.kalshi.com/api-reference/portfolio/get-balance.md, .../get-positions.md, .../get-fills.md, https://docs.kalshi.com/api-reference/orders/get-orders.md, .../create-order.md, .../cancel-order.md (scraped 2026-05-30)

# Portfolio and Orders

All endpoints below require authentication (`KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-SIGNATURE`, `KALSHI-ACCESS-TIMESTAMP`). Many accept a `subaccount` query parameter (0 = primary, 1–32 = subaccounts).

---

## Get Balance

`GET /portfolio/balance`

### Query Parameters

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `subaccount` | integer | No | 0 | Subaccount number (0 = primary, 1–32). |

### Response

```json
{
  "balance": 0,
  "balance_dollars": "0.0000",
  "portfolio_value": 0,
  "updated_ts": 0,
  "balance_breakdown": [ { "exchange_index": 0, "balance": "0.0000" } ]
}
```

| Field | Type | Description |
|---|---|---|
| `balance` | int64 | Available balance **in cents** (amount available for trading). |
| `balance_dollars` | string | Balance as fixed-point dollars (up to 6 decimals). |
| `portfolio_value` | int64 | Portfolio value **in cents** (current value of all positions). |
| `updated_ts` | int64 | Unix timestamp of last balance update. |
| `balance_breakdown` | array | Balance per exchange index. |

---

## Get Positions

`GET /portfolio/positions`

### Query Parameters

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `cursor` | string | No | — | Pagination cursor. |
| `limit` | integer | No | 100 | Results per page (1–1000). |
| `count_filter` | string | No | — | Comma-separated; restrict to positions with non-zero values in any of: `position`, `total_traded`. |
| `ticker` | string | No | — | Filter by market ticker. |
| `event_ticker` | string | No | — | Filter by event ticker (single only). |
| `subaccount` | integer | No | 0 | Subaccount number. |

### Response

```json
{
  "cursor": "string",
  "market_positions": [
    {
      "ticker": "string",
      "total_traded_dollars": "1500.500000",
      "position_fp": "25.00",
      "market_exposure_dollars": "2000.000000",
      "realized_pnl_dollars": "150.250000",
      "resting_orders_count": 2,
      "fees_paid_dollars": "25.000000",
      "last_updated_ts": "2024-01-15T10:30:00Z"
    }
  ],
  "event_positions": [
    {
      "event_ticker": "string",
      "total_cost_dollars": "500.000000",
      "total_cost_shares_fp": "50.00",
      "event_exposure_dollars": "750.000000",
      "realized_pnl_dollars": "75.500000",
      "fees_paid_dollars": "10.000000"
    }
  ]
}
```

**market_positions fields:** `ticker`, `total_traded_dollars`, `position_fp` (signed contract count; positive = YES/long, negative = NO/short), `market_exposure_dollars`, `realized_pnl_dollars`, `resting_orders_count` (deprecated), `fees_paid_dollars`, `last_updated_ts`.
**event_positions fields:** `event_ticker`, `total_cost_dollars`, `total_cost_shares_fp`, `event_exposure_dollars`, `realized_pnl_dollars`, `fees_paid_dollars`.

**Status codes:** 200, 400, 401, 500.

---

## Get Fills

`GET /portfolio/fills`

Returns the authenticated user's individual fills (executions).

### Query Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `ticker` | string | No | Filter by market ticker. |
| `order_id` | string | No | Filter by order ID. |
| `min_ts` | integer (int64) | No | Filter items after this Unix timestamp. |
| `max_ts` | integer (int64) | No | Filter items before this Unix timestamp. |
| `limit` | integer (int64) | No | Results per page. Default 100 (1–1000). |
| `cursor` | string | No | Pagination cursor. |
| `subaccount` | integer | No | Subaccount number; defaults to all subaccounts if omitted. |

### Response

```json
{
  "fills": [
    {
      "fill_id": "string",
      "trade_id": "string",
      "order_id": "string",
      "ticker": "string",
      "market_ticker": "string",
      "side": "yes|no",
      "action": "buy|sell",
      "outcome_side": "yes|no",
      "book_side": "bid|ask",
      "count_fp": "10.00",
      "yes_price_dollars": "0.5600",
      "no_price_dollars": "0.4400",
      "is_taker": true,
      "created_time": "2024-01-01T00:00:00Z",
      "fee_cost": "0.010000",
      "subaccount_number": 0,
      "ts": 1704067200000
    }
  ],
  "cursor": "string"
}
```

| Field | Description |
|---|---|
| `fill_id` / `trade_id` / `order_id` | Identifiers for the fill, trade, and originating order. |
| `ticker` / `market_ticker` | Market identifier. |
| `side` / `outcome_side` | `yes` or `no`. |
| `action` | `buy` or `sell`. |
| `book_side` | `bid` or `ask`. |
| `count_fp` | Contracts filled (fixed-point string). |
| `yes_price_dollars` / `no_price_dollars` | Fill prices (sum to $1.00). |
| `is_taker` | True if this fill was the aggressing (taker) side. |
| `fee_cost` | Fee charged for this fill, in dollars (fixed-point). |
| `created_time` / `ts` | ISO timestamp / Unix-millisecond timestamp. |

---

## Get Orders

`GET /portfolio/orders`

### Query Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `ticker` | string | No | Filter by market ticker. |
| `event_ticker` | string | No | Event tickers (comma-separated, max 10). |
| `status` | string | No | Filter: `resting`, `canceled`, or `executed`. |
| `cursor` | string | No | Pagination cursor. |
| `limit` | integer | No | Results per page (1–1000, default 100). |
| `min_ts` | integer | No | Filter items after this Unix timestamp. |
| `max_ts` | integer | No | Filter items before this Unix timestamp. |
| `subaccount` | integer | No | Subaccount number (0 = primary, 1–32). |

### Response

```json
{
  "orders": [
    {
      "order_id": "string",
      "user_id": "string",
      "client_order_id": "string",
      "ticker": "string",
      "side": "yes|no",
      "action": "buy|sell",
      "outcome_side": "yes|no",
      "book_side": "bid|ask",
      "type": "limit|market",
      "status": "resting|canceled|executed",
      "yes_price_dollars": "0.5600",
      "no_price_dollars": "0.5600",
      "fill_count_fp": "10.00",
      "remaining_count_fp": "5.00",
      "initial_count_fp": "15.00",
      "taker_fees_dollars": "0.100000",
      "maker_fees_dollars": "0.050000",
      "taker_fill_cost_dollars": "5.000000",
      "maker_fill_cost_dollars": "3.500000",
      "expiration_time": "2024-12-31T23:59:59Z",
      "created_time": "2024-01-01T00:00:00Z",
      "last_update_time": "2024-01-01T12:30:00Z",
      "self_trade_prevention_type": "taker_at_cross|maker",
      "order_group_id": "string",
      "cancel_order_on_pause": true,
      "subaccount_number": 0,
      "exchange_index": 0
    }
  ],
  "cursor": "string"
}
```

> Related: `GET /portfolio/orders/{order_id}` (Get Order).

---

## Create Order

`POST /portfolio/orders`

Places a limit or market order. The order type is determined implicitly: providing a price (`yes_price`/`no_price`/`*_price_dollars`) yields a **limit** order; omitting price yields a **market** order.

### Request Body

```json
{
  "ticker": "string (required, min length 1)",
  "side": "yes | no (required)",
  "action": "buy | sell (required)",
  "client_order_id": "string (optional)",
  "count": "integer (optional, minimum 1)",
  "count_fp": "string (optional, fixed-point, 0-2 decimals)",
  "yes_price": "integer (optional, 1-99)",
  "no_price": "integer (optional, 1-99)",
  "yes_price_dollars": "string (optional, fixed-point up to 6 decimals)",
  "no_price_dollars": "string (optional, fixed-point up to 6 decimals)",
  "expiration_ts": "integer (optional, Unix seconds)",
  "time_in_force": "fill_or_kill | good_till_canceled | immediate_or_cancel (optional)",
  "buy_max_cost": "integer (optional, cents; enforces Fill-or-Kill)",
  "post_only": "boolean (optional)",
  "reduce_only": "boolean (optional)",
  "sell_position_floor": "integer (deprecated, only accepts 0)",
  "self_trade_prevention_type": "taker_at_cross | maker (optional)",
  "order_group_id": "string (optional)",
  "cancel_order_on_pause": "boolean (optional)",
  "subaccount": "integer (optional, default 0, range 0-32)",
  "exchange_index": "integer (optional, default 0)"
}
```

### Field descriptions

- `ticker` — Market identifier (required).
- `side` — `yes` or `no` outcome (required).
- `action` — `buy` or `sell` direction (required).
- `client_order_id` — Custom identifier for tracking.
- `count` — Order quantity in whole contracts.
- `count_fp` — Quantity as a fixed-point string; 0–2 decimals in requests, always 2 in responses. Provide either `count` or `count_fp`; if both, they must match.
- `yes_price` / `no_price` — Price in cents (legacy, 1–99).
- `yes_price_dollars` / `no_price_dollars` — Price in fixed-point dollars.
- `expiration_ts` — Unix-second expiration; use with `good_till_canceled`. Cannot combine `immediate_or_cancel` with `expiration_ts`.
- `time_in_force` — Order duration behavior.
- `buy_max_cost` — Max spend in cents; automatically applies Fill-or-Kill.
- `post_only` — Adds liquidity only; rejected if it would execute immediately.
- `reduce_only` — Can only reduce an existing position.
- `sell_position_floor` — Deprecated; superseded by `reduce_only` (only accepts 0).
- `self_trade_prevention_type` — `taker_at_cross` cancels the incoming order; `maker` cancels the resting order.
- `order_group_id` — Links order to an order group.
- `cancel_order_on_pause` — Auto-cancel if the exchange pauses trading.
- `subaccount` / `exchange_index` — Subaccount (0 primary) / exchange shard (only 0 supported).

### Response

```json
{ "order": { /* Order object, same schema as in Get Orders, including outcome_side, book_side, fill/remaining/initial_count_fp, fee and cost fields */ } }
```

### Status codes & constraints

- **201** Created; **400** Bad request; **401** Unauthorized; **409** Conflict; **429** Rate limit exceeded (10 tokens per request default); **500** Internal error.
- Each user is limited to **200,000 open orders** simultaneously.
- Fractional contracts supported on enabled markets; minimum granularity 0.01.

> Related: `POST /portfolio/orders/batch` (Batch Create Orders), Amend, Decrease, and `create-order-v2` variants.

---

## Cancel Order

`DELETE /portfolio/orders/{order_id}`

Cancels (reduces completely) a resting order, zeroing the remaining resting contracts on it.

### Parameters

| Name | Type | Location | Required | Description |
|---|---|---|---|---|
| `order_id` | string | path | Yes | Order ID. |
| `subaccount` | integer | query | No | Subaccount number (default 0). |
| `exchange_index` | integer | query | No | Exchange shard identifier (default 0). |

### Response

```json
{
  "order": { /* Order object (same schema as Get Orders) */ },
  "reduced_by_fp": "string"
}
```

`reduced_by_fp` = number of contracts removed from the resting order by the cancel.

**Status codes:** 200, 401 Unauthorized, 404 Not Found, 500. **Rate limit:** 2 tokens per request.

> Related: `POST /portfolio/orders/batched/cancel` (Batch Cancel Orders).
