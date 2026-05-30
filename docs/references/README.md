# References

Vendored external knowledge for the Kalshi autoresearch agent. These files are
**reference material, not canonical project docs** — the source of truth for what
we build lives in `../DESIGN.md` and `../TASKS.md`. Keep this folder for "look it
up locally instead of re-fetching the web" needs.

## Contents

### `kalshi/` — Kalshi Trade API v2 docs

A curated scrape of <https://docs.kalshi.com> (2026-05-30), trimmed to what this
project needs to read markets and (later) paper/live trade. Enough to implement a
client without opening a browser.

| File | Covers |
|---|---|
| `overview.md` | Event contracts, YES/NO mechanics, cents pricing |
| `api-environments.md` | Production vs demo base URLs, `/trade-api/v2` prefix |
| `authentication.md` | RSA-PSS request signing, the three `KALSHI-ACCESS-*` headers |
| `markets.md` | Get Markets / Market / Event / Series + response schemas |
| `orderbook.md` | Bids-only book, implied-ask math, single + bulk endpoints |
| `trades-candlesticks.md` | Get Trades, Get Candlesticks |
| `portfolio-orders.md` | Balance, positions, orders, fills, create/cancel order |
| `rate-limits-and-fees.md` | Rate-limit tiers and the trading-fee formula |
| `websocket.md` | Streaming feed: channels, subscribe, auth |

Our own client (`../../kalshi_client.py`) already implements the auth signing
described in `authentication.md`. Note the docs list `external-api.kalshi.com` as
the current production host; `api.elections.kalshi.com` (what our client uses) is a
still-working legacy alias for the same exchange — both serve **all** markets.

### `autoresearch/` — Karpathy's autonomous research loop

A cleaned copy of [karpathy/autoresearch](https://github.com/karpathy/autoresearch)
(MIT). We kept the **methodology** and dropped the nanochat GPU training code,
which is not relevant here. This is the conceptual template for the "agent iterates
on trading strategies against a frozen backtester" half of our design.

| File | What it is |
|---|---|
| `README.md` | How the autoresearch loop maps onto our Kalshi backtester |
| `program.md` | Karpathy's original agent loop (verbatim) — the keep/discard engine |
| `upstream-README.md` | Karpathy's original README — the philosophy and design choices |

## Provenance

- Kalshi docs: scraped from docs.kalshi.com on 2026-05-30. Spot-check against the
  live site before relying on exact response fields for trading code.
- autoresearch: `git clone` of `karpathy/autoresearch` @ master (pushed 2026-03-26),
  MIT licensed. Full repo (incl. `train.py`, `prepare.py`, `analysis.ipynb`) at the
  upstream URL above.
