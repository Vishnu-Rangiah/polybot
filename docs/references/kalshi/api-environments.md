> Source: https://docs.kalshi.com/getting_started/api_environments.md (scraped 2026-05-30)

# API Environments and Endpoints

Kalshi operates separate **production** and **demo** environments, each with distinct credentials and endpoints for REST and WebSocket connections. API keys are environment-specific.

All REST paths share the `/trade-api/v2` prefix. WebSocket paths use the `/trade-api/ws/v2` prefix.

## REST API Base URLs

| Environment | Primary (recommended) | Alternative (legacy) |
|---|---|---|
| Production | `https://external-api.kalshi.com/trade-api/v2` | `https://api.elections.kalshi.com/trade-api/v2` |
| Demo | `https://external-api.demo.kalshi.co/trade-api/v2` | `https://demo-api.kalshi.co/trade-api/v2` |

- The `external-api` hosts are recommended for API traders; the legacy hosts remain available for backward compatibility.
- **Note on the elections domain:** Despite the `elections` subdomain, the production Trade API provides access to **all** Kalshi markets, not only election-related markets.

## WebSocket API Base URLs

| Environment | Primary (recommended) | Alternative (legacy) |
|---|---|---|
| Production | `wss://external-api-ws.kalshi.com/trade-api/ws/v2` | `wss://api.elections.kalshi.com/trade-api/ws/v2` |
| Demo | `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2` | `wss://demo-api.kalshi.co/trade-api/ws/v2` |

## Demo Environment

The demo environment lets you test without real funds. Sign up for a demo account, generate demo-specific API keys, and point the base URL at the demo host. Behavior mirrors production for trading flows.

## Request Signing Note

When signing requests (see `authentication.md`), use only the URL **path including the `/trade-api/v2` prefix and excluding query parameters**. For example, sign `/trade-api/v2/portfolio/orders` rather than the full URL or the query string. For WebSockets, sign the path `/trade-api/ws/v2`.
