# Kalshi Trade API v2 — Reference

Curated scrape of <https://docs.kalshi.com> (2026-05-30). Read these locally
instead of re-fetching the site. For trading-critical response fields, spot-check
against the live docs first — schemas drift.

## Read order

1. `overview.md` — what an event contract is, YES/NO = $1.00, prices in cents.
2. `api-environments.md` — base URLs and the `/trade-api/v2` prefix.
3. `authentication.md` — RSA-PSS signing and the `KALSHI-ACCESS-*` headers.
4. `markets.md` / `orderbook.md` — the data this project reads first.
5. `portfolio-orders.md` — balance/positions/orders (auth required).
6. `trades-candlesticks.md`, `rate-limits-and-fees.md`, `websocket.md` — as needed.

## The five mechanics that bite

These are the easy-to-miss rules our `DESIGN.md` calls out. Details in the files.

- **Sign the path, not the query.** Signing string is `timestamp + METHOD + path`,
  path includes `/trade-api/v2`, query string excluded. Timestamp in **ms**.
  (`authentication.md`)
- **The book is bids-only.** No asks are published. Derive them:
  `yes_ask = 1 − best_no_bid`, `no_ask = 1 − best_yes_bid`. (`orderbook.md`)
- **Resolution rule > title.** The exact settlement criteria, not the market
  title, controls payout. (`markets.md`, `overview.md`)
- **Fees + spread can erase edge.** Round-up-to-the-cent parabolic fee, plus the
  spread you cross. (`rate-limits-and-fees.md`)
- **Public vs authenticated.** Market data is public; portfolio/orders/fills need
  the signed headers. (`authentication.md`, `portfolio-orders.md`)

## Base URLs (quick copy)

```
Production : https://api.elections.kalshi.com/trade-api/v2   (legacy alias, what kalshi_client.py uses)
Production : https://external-api.kalshi.com/trade-api/v2     (current host per docs)
Demo       : https://demo-api.kalshi.co/trade-api/v2
```
