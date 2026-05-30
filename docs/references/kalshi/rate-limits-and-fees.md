> Source: https://docs.kalshi.com/getting_started/rate_limits.md, https://docs.kalshi.com/getting_started/fee_rounding.md, https://help.kalshi.com/trading/fees, https://kalshi.com/docs/kalshi-fee-schedule.pdf (scraped 2026-05-30)

# Rate Limits and Fees

## Rate Limits

Kalshi uses a **token-budget** system. Your tier defines how many tokens you can spend per second. Most operations cost **10 tokens**; some cheaper operations (order cancellations, single-order reads, quote operations, multivariate-collection lookups) cost fewer (e.g. cancel = 2 tokens). Your effective request rate = budget ÷ operation cost.

### Two independent buckets

- **Read bucket** — GET endpoints and operations not routed elsewhere.
- **Write bucket** — order placement, amendments, cancellations, order groups, and RFQ quote flows.

### Tiers

| Tier | Read budget (tokens/sec) | Write budget (tokens/sec) |
|---|---|---|
| Basic | 200 | 100 |
| Advanced | 300 | 300 |
| Premier | 1,000 | 1,000 |
| Paragon | 2,000 | 2,000 |
| Prime | 4,000 | 4,000 |

**Qualification:** Basic is automatic on signup. Advanced requires completing the Advanced API application form. Premier / Paragon / Prime qualification criteria "will be published shortly." Members can request upgrades by contacting support with their use case.

### Batch operations

Batch requests cost the same as the equivalent individual calls. Example: batch-create of 25 orders = 250 tokens (25 × 10); batch-cancel of 25 orders = 50 tokens (25 × 2).

### Burst capacity

The Write bucket can accumulate up to two seconds of per-second budget during idle periods, allowing a single burst above steady state. Basic tier's Write bucket holds only one second with no accumulation.

### 429 response

When limits are exceeded, the API returns **HTTP 429 Too Many Requests** with body `{"error": "too many requests"}`. There are currently no `Retry-After` or `X-RateLimit` headers; clients should apply exponential backoff.

> Endpoint-specific costs can be queried via `GET /account/api_limits` (Get Account API Limits) and `list-non-default-endpoint-costs`.

---

## Trading Fees

Kalshi charges a transaction (trading) fee based on the expected earnings of the contract. The fee is a **parabolic** function of price — highest near 50¢ and decreasing toward 1¢ and 99¢.

### Taker (general) fee formula

```
fees = round_up( 0.07 × C × P × (1 − P) )
```

Where:
- `C` = number of contracts traded.
- `P` = price of a contract **in dollars** (50¢ → `P = 0.50`).
- `round_up` = round up to the next cent ($0.01).

### Maker fee formula

```
fees = round_up( 0.0175 × C × P × (1 − P) )
```

Maker fees apply to orders that rest on the book (not immediately matched) and are roughly one quarter of the taker fee. Whether maker fees apply depends on the series `fee_type` (`quadratic` = taker-only; `quadratic_with_maker_fees` = both maker and taker; `flat`).

### Per-contract fee examples (taker)

| Price P | 0.07 × P × (1 − P) | Fee per contract (round up to cent) |
|---|---|---|
| $0.50 | 0.0175 | $0.0175 (maximum) |
| $0.10 | 0.0063 | $0.0063 |
| $0.90 | 0.0063 | $0.0063 |

> The fee is highest at 50¢ and decreases symmetrically toward both ends of the price range. Series-level `fee_multiplier` / `fee_type` (and per-event `fee_type_override` / `fee_multiplier_override`) can adjust the effective fee for specific markets. The authoritative, current schedule is the Kalshi Fee Schedule PDF: https://kalshi.com/docs/kalshi-fee-schedule.pdf

### Fee Rounding

Trade fees are computed and then rounded so balances hit a target precision:

- **Direct members:** balances rounded to the nearest **$0.0001** (0.01¢).
- **Non-direct members:** balances rounded to the nearest **$0.01** (1¢).

Each fill has three fee components:
- **Trade fee** — rounded up to the nearest $0.0001.
- **Rounding fee** — adjustment to restore the target precision:
  ```
  balance_change = revenue − trade_fee
  rounding_fee   = balance_change − floor(balance_change)
  ```
- **Rebate** — refund from accumulated overpayment, always a multiple of $0.01.

An internal accumulator tracks fractional overpayment across fills and triggers whole-cent rebates over time.
