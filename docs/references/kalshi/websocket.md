> Source: https://docs.kalshi.com/getting_started/quick_start_websockets.md, https://docs.kalshi.com/websockets/websocket-connection.md (scraped 2026-05-30)

# WebSocket Feed

A single WebSocket connection carries all real-time communication. Subscribe to one or more channels over that connection.

## Connection URLs

| Environment | Primary | Legacy |
|---|---|---|
| Production | `wss://external-api-ws.kalshi.com/trade-api/ws/v2` | `wss://api.elections.kalshi.com/trade-api/ws/v2` |
| Demo | `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2` | `wss://demo-api.kalshi.co/trade-api/ws/v2` |

## Authentication

Authentication is required to establish the connection — include the same RSA API-key headers used for REST during the WebSocket **handshake (upgrade request)**:

```
KALSHI-ACCESS-KEY: your_api_key_id
KALSHI-ACCESS-SIGNATURE: request_signature
KALSHI-ACCESS-TIMESTAMP: unix_timestamp_in_milliseconds
```

### Signature

Build the signing string exactly as for REST, but with the WebSocket path:

```
timestamp + "GET" + "/trade-api/ws/v2"
```

Sign with the RSA private key using PSS padding + SHA-256, then Base64-encode. (See `authentication.md`.)

## Channels

Public market-data channels:
- `ticker` — best bid/ask price updates.
- `trade` — public trade executions.
- `market_lifecycle_v2`, `multivariate_market_lifecycle`, `multivariate` — market/event lifecycle events.

Private channels (require authentication):
- `orderbook_delta` — incremental orderbook updates (with an initial snapshot).
- `fill` — your fills.
- `market_positions` — your position updates.
- `user_orders` — your order updates.
- `communications`, `order_group_updates`.

## Commands

### Subscribe

```json
{
  "id": 1,
  "cmd": "subscribe",
  "params": {
    "channels": ["orderbook_delta"],
    "market_tickers": ["KXHARRIS24-LSV"]
  }
}
```

`params` fields:
- `channels` (array, required) — channels to subscribe to.
- `market_ticker` (string) / `market_tickers` (array) — single / multiple markets.
- `market_id` (string) / `market_ids` (array) — UUID-based market subscription.
- `send_initial_snapshot` (boolean) — receive an initial snapshot on the `ticker` channel.
- `skip_ticker_ack` (boolean) — OK responses omit the market_tickers/ids list.
- `use_yes_price` (boolean) — orderbook channel only; report no-side updates in yes-leg pricing.
- `shard_factor` / `shard_key` (integer) — communications channel fanout sharding.

Each command has a client-generated `id` that must be unique within the session.

### Unsubscribe

```json
{ "id": 124, "cmd": "unsubscribe", "params": { "sids": [1, 2] } }
```

### List subscriptions

```json
{ "id": 3, "cmd": "list_subscriptions" }
```

### Update subscription

```json
{
  "id": 124,
  "cmd": "update_subscription",
  "params": {
    "sids": [456],
    "market_tickers": ["NEW-MARKET-1", "NEW-MARKET-2"],
    "action": "add_markets"
  }
}
```

`action` is one of `add_markets`, `delete_markets`, or `get_snapshot`. Use `sid` (single) or `sids` (multiple).

## Server Responses

Subscription confirmed:
```json
{ "id": 1, "type": "subscribed", "msg": { "channel": "orderbook_delta", "sid": 1 } }
```

Update confirmed:
```json
{ "id": 123, "sid": 456, "seq": 222, "type": "ok", "msg": { "market_tickers": ["MARKET-1", "MARKET-2"] } }
```

Error:
```json
{ "id": 123, "type": "error", "msg": { "code": 6, "msg": "Already subscribed" } }
```

Error codes range 1–22 (e.g. general processing error, params required, auth failure, unknown command, already subscribed, market errors).

## Example Data Messages

Ticker:
```json
{ "type": "ticker", "msg": { "market_ticker": "KXHARRIS24-LSV", "yes_bid_dollars": 0.45, "yes_ask_dollars": 0.55 } }
```

Orderbook snapshot / delta:
```json
{ "type": "orderbook_snapshot", "msg": { "market_ticker": "KXHARRIS24-LSV" } }
{ "type": "orderbook_delta",    "msg": { "market_ticker": "KXHARRIS24-LSV", "client_order_id": "optional_if_user_caused" } }
```

> Keep the connection alive with periodic pings (see Connection Keep-Alive in the docs). Each subscription has a `seq` sequence number on the `orderbook_delta` channel; gaps mean you should resubscribe to get a fresh snapshot.
```

---

## Summary

I scraped the Kalshi docs (using the `.md` versions of each page, discovered via `https://docs.kalshi.com/llms.txt`) and produced all 9 requested reference files, returned above with `
