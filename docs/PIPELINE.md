# Pipeline: Data In, Orders Out

How `kalshi_agent/` is built. The research/agent framing lives in `DESIGN.md`;
this doc is the **data ingestion + trade execution** architecture and the live
Kalshi field mappings. Read this before building the backtester or going live.

## The one idea

Everything rests on **two narrow interfaces** with Kalshi behind them:

```
   data in  ──▶  DataSource  ──▶  MarketState   (your type)
  orders out ◀──  Executor   ◀──  Order          (your type)
```

Strategy, risk, and the research agent speak only `MarketState` and `Order` —
never raw Kalshi JSON. That single rule is what makes **live, paper, and
backtest** three swappable implementations of the same two interfaces. Going
from paper to live is constructing a different object, not a refactor.

## Layers (low → high)

| Module | Responsibility | Knows about… |
|--------|----------------|--------------|
| `transport.py` | signing, HTTP, retry/backoff, rate limit, WS handshake | `requests`, URLs, RSA |
| `normalize.py` | raw Kalshi JSON → `MarketState` | Kalshi wire format |
| `datasource.py` | `DataSource` protocol; REST poller + WebSocket source | `transport`, `normalize` |
| `store.py` | append-only JSONL snapshot log | `MarketState` only |
| `risk.py` | pre-trade gate (limits, kill-switch) | `Order`, `Position` |
| `executor.py` | `Executor` protocol; Paper + Live | `transport`, `risk` |
| `strategy.py` | `decide(state) -> Order \| None` | `MarketState`, `Order` |
| `run.py` | wires it together (demo) | everything |

Two boundaries do the heavy lifting:
- **`transport.py` is the only file that imports `requests`.** Nothing above it
  sees a status code or a network exception.
- **`normalize.py` is the only file that knows Kalshi's wire format.** If Kalshi
  renames a field, this is the one place to edit.

## Data flow

```
              ┌── RestDataSource ──┐
 Kalshi REST ─┤                    ├─▶ normalize() ─▶ MarketState ─┬─▶ strategy.decide()
 Kalshi WS  ──┴── WebSocketDataSrc ┘                              └─▶ store.append()  (= backtest data)
                                                                        │
                          Order ◀───────────────────────────────────────┘
                            │
                            ▼
                        RiskGate.check()  ──reject──▶ (no trade)
                            │ approve
                            ▼
                  PaperExecutor / LiveExecutor ─▶ Fill
```

### Two data sources, one interface

- **`RestDataSource`** — request/response polling. Right for startup, sanity
  checks, low-frequency markets. Stamps `observed_at_ms` at fetch time.
- **`WebSocketDataSource`** — Kalshi's push feed (`orderbook_snapshot` then a
  stream of `orderbook_delta`). A background thread folds deltas into an
  in-memory book; `get_state()` reads the current best levels. **The push feed
  is hidden behind the same pull interface** — the strategy can't tell which
  source fed it. Book maintenance (`_handle`) is separated from the socket so it
  is unit-tested with synthetic messages, no network.

### Snapshots are backtest data, for free

Every `MarketState` the bot observes gets written to `outputs/snapshots.jsonl`
via `SnapshotStore.append()`. Historical replay is just reading that log back in
`observed_at_ms` order:

```python
for state in SnapshotStore("outputs/snapshots.jsonl").replay():
    order = strategy.decide(state)   # no-lookahead: state only carries data observed at that time
```

**This is the seam the backtester builds on.** `backtest(strategy_fn, split)`
iterates `replay()`, calls `decide()`, and fills against a `PaperExecutor`. No
new data plumbing needed — the live recorder already produced the dataset.

## Execution: trading efficiently + safely

`Executor` is one method: `submit(order, *, state) -> Fill | None`.

- **`PaperExecutor`** — fills against the observed book in memory. No network,
  no real money. The "paper-only" guardrail is **structural**: `run.py`
  constructs this; you can't accidentally trade live.
- **`LiveExecutor`** — POSTs to Kalshi, carrying the idempotency key.

Three safety properties are architectural, not optional features:

1. **Risk gate between decision and execution.** Both executors call
   `RiskGate.check()` before any fill/POST. Limits: per-order size, per-market
   position, per-order notional, balance, and a `kill_switch`. The strategy
   proposes; the gate disposes.
2. **Idempotency baked into the type.** `Order.client_order_id` auto-generates
   and rides along on the live POST body, so a retried submit can't double-fill.
3. **Exchange is source of truth.** `LiveExecutor` reads positions/balance from
   `/portfolio`, never from local guesses, so the bot's view can't silently
   diverge from Kalshi's.

## Concurrency

The live path is naturally **event-driven**: a WS push updates the book; a
trading loop periodically (or on tick) calls `get_state → decide → check →
submit`. The WebSocket runs its own daemon thread; book reads/writes are guarded
by a lock. If this grows, an `asyncio` loop is the natural home — almost all the
work is I/O wait.

## Live Kalshi field mappings (VERIFIED against prod, 2026-05-30)

The Kalshi-specific facts, isolated to `normalize.py`, `datasource.py`, and
`executor.py`. **These were checked against the live prod API, not just docs —
and reality differed from every doc/reference client.** The feeds use
dollar-strings under inconsistent key names; `normalize.parse_levels` accepts all
variants and emits integer cents.

**REST orderbook** (`GET /markets/{ticker}/orderbook`) — actual response:
```json
{ "orderbook_fp": { "yes_dollars": [["0.9880", "9333.00"], ...],
                    "no_dollars":  [["0.9480", "216.00"], ...] } }
```
Top-level key is `orderbook_fp` (not `orderbook`); levels are `[price_dollars,
qty]` **strings**. Kalshi quotes only YES/NO **bids**; asks derived once:
```
yes_ask = 100 - best_no_bid        no_ask = 100 - best_yes_bid
```
Best bid is chosen by **max price**, not array position (order isn't guaranteed).

**WebSocket** (`wss://api.elections.kalshi.com/trade-api/ws/v2`) — actual messages:
- Handshake signed like a REST `GET` of `/trade-api/ws/v2`. ✅ verified working.
- Subscribe: `{"id","cmd":"subscribe","params":{"channels":["orderbook_delta"],"market_ticker":"…"}}`.
- `subscribed` ack arrives first, then `orderbook_snapshot`, then `orderbook_delta`s.
  **Readiness must wait for the snapshot, not the ack** (else the book is empty).
- Snapshot `msg`: `{market_ticker, yes_dollars_fp[[p,q]], no_dollars_fp[[p,q]]}`
  — note the `_fp` suffix, *different from REST's* `yes_dollars`.
- Delta `msg`: `{market_ticker, price_dollars, delta_fp, side, ts_ms}` — apply
  `level[price] += delta`, drop the level at `<= 0`.

**Create order** (`POST /portfolio/orders`) — *not yet placed live* (see below):
- Request: `ticker, side, action, count, type:"limit", yes_price|no_price (cents), client_order_id`.
- Response `order`: filled count is `fill_count_fp`, id is `order_id`,
  fees are `taker_fees_dollars`.

**Positions** (`GET /portfolio/positions`):
- `market_positions[].position_fp` is the **signed** net (＋ = YES, − = NO).
  Parse with `_fp_to_int`. Dollar fields (`*_dollars`) → `_dollars_to_cents`.

### Verification status
- ✅ REST auth, balance, markets, orderbook → `MarketState`.
- ✅ WebSocket handshake, subscribe, snapshot+delta book maintenance; WS and REST
  produce a consistent `MarketState` (same derived prices) for the same market.
- ✅ **Order placement validated live on demo (2026-05-30).**
  `uv run -m kalshi_agent.smoke --env demo --rest-and-cancel` ran the full
  lifecycle: `place` (POST → real `order_id`, `status=resting`, `fill_count_fp`
  parsed), confirm, then `cancel` (DELETE → `status=canceled`, `reduced_by_fp`).
  `type:"limit"` is accepted; a 1¢ YES rests as expected (`yes_price_dollars:
  "0.0100"`). The account was left with **0 resting orders**. Confirmed quirk:
  the by-id read `GET /portfolio/orders/{id}` lags a few seconds on demo after
  placing (transient 404); the resting-orders **list** is consistent immediately,
  so the smoke test retries by-id then falls back to the list, and always cancels
  regardless so nothing is left resting.
- ⏸️ **Not yet exercised:** a real *fill* (we only rested+canceled), so
  `fill_count_fp` parsing for a non-zero fill and the exact taker fill price are
  still unconfirmed end-to-end (covered offline in `tests/test_executor.py`).
  **`--env prod --place-order` trades real money — see `CREDENTIALS.md`.**

## Deliberate divergences from `DESIGN.md`

- **Prices are integer cents**, not floats — money never touches floating point.
  `MarketState` price fields are typed accordingly.
- **`Order`** carries `action` + `client_order_id` (idempotency), richer than the
  doc's sketch. `decide()` still returns `Order | None`.

## Run it

```bash
uv run -m kalshi_agent.run                 # paper loop on a built-in fixture (no network)
uv run -m kalshi_agent.run --ticker TICK   # live data, still paper execution
uv run python tests/test_pipeline.py       # the test suite (no network, no pytest needed)

uv run -m kalshi_agent.smoke --env demo    # live REST + WS round-trip against DEMO (no real money)
uv run -m kalshi_agent.smoke --env demo --place-order # + places ONE 1-contract demo order
uv run -m kalshi_agent.smoke --env prod    # ⚠️ hits the LIVE prod account — see CREDENTIALS.md
```

**Credentials:** `.env.local` is wired to the **demo read-write** key by default
(paper environment, no real money). Demo and prod are separate accounts with
separate keys; both write-scoped keys are configured. Switching to prod trades
**real money** — see `CREDENTIALS.md` for the keys, the env switch, and the
warning.
