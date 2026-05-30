> Source: https://docs.kalshi.com/welcome/index.md, https://help.kalshi.com/en/articles/13823763-what-is-kalshi, https://docs.kalshi.com/getting_started/terms.md (scraped 2026-05-30)

# Kalshi Overview

## What Kalshi Is

Kalshi is a federally regulated prediction-market exchange in the United States. It pioneered a new asset class called **event contracts**, which let traders express opinions on the outcome of real-world, yes/no questions ("Will an event happen, or won't it?").

The Kalshi Exchange API provides real-time market data and trade execution. Through the API you can access:

- All markets' order books and market statistics.
- Your own orders, trades, portfolio, and portfolio history.
- Real-time streaming data over WebSockets.

> Despite the `elections` subdomain on one of the production hosts, the production Trade API provides access to **all** Kalshi markets — economics, climate, technology, entertainment, sports, crypto, weather, and more — not just election-related markets.

## Event Contracts and YES/NO Binary Mechanics

An event contract is a binary instrument tied to a yes/no question about a real-world outcome.

- Every market has two sides: **YES** and **NO**.
- When two users match, one receives a YES contract and the other receives a NO contract. Together they pay a total of **$1.00** (the collateral).
- At settlement, a contract pays out **$1.00** if its side is correct, and **$0.00** if it is not.
  - If the event resolves YES, each YES contract pays $1.00 and each NO contract pays $0.00.
  - If the event resolves NO, each NO contract pays $1.00 and each YES contract pays $0.00.
- Because the two sides sum to the $1.00 payout, **YES price + NO price = $1.00** at all times.

## Pricing in Cents

- Contract prices range from **$0.01 to $0.99** (1¢ to 99¢). Legacy integer price fields use the range **1–99 cents**.
- The price of a contract directly reflects the **implied probability** of the outcome. A market priced at 40¢ implies roughly a 40% chance of resolving YES; the expected value of a YES contract is then 40¢.
- Because YES + NO = $1.00, a YES bid at price X is economically equivalent to a NO ask at ($1.00 − X), and vice versa (see `orderbook.md`).

### Fixed-Point Price/Quantity Representation

The current API expresses monetary values and quantities as fixed-point **strings**:

- `*_dollars` fields are dollar amounts as decimal strings with up to 6 decimal places (e.g. `"0.5600"` = $0.56, i.e. 56¢).
- `*_fp` fields are contract counts as fixed-point decimal strings, typically with 2 decimal places (e.g. `"10.00"` = 10 contracts). Markets with fractional trading enabled support a minimum granularity of 0.01 contracts.
- Some legacy integer fields remain: `*_price` in cents (1–99), `balance`/`portfolio_value` in cents.

## Object Hierarchy (Glossary)

- **Category** — A high-level discovery grouping for related series, such as sports, crypto, or weather.
- **Subcategory** — A narrower discovery grouping within a category. A series can belong to multiple subcategories.
- **Series** — A collection of related events. Each event examines comparable data across distinct time periods, the events have no logical dependencies between them, and all events in a series share the same ticker prefix.
- **Event** — A collection of markets, and the basic unit that members should interact with on Kalshi. An event can be *mutually exclusive* (only one market resolves YES) or not.
- **Market** — A single binary market. This is a low-level object that rarely needs to be exposed on its own to members.

Ticker relationships: a series has a ticker prefix; events belong to a series (`series_ticker`); markets belong to an event (`event_ticker`) and have their own `ticker`.
