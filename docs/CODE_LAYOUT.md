# Code Layout

Polybot has **one package** (`kalshi_agent/`) and **one CLI** (`polybot`). Root-level Python files are limited to thin compatibility shims for `read.py` and `kalshi_client.py`.

## What to run

```bash
uv sync
uv run polybot --help

# Paper trading demo (no network)
uv run polybot run

# Signed Kalshi auth smoke test (.env.local)
uv run polybot read

# Weather research memo (public Kalshi + NWS)
uv run polybot research --ticker KXRAINNYC-26MAY31-T0

# OpenAI Agents coordinator
uv run polybot agent --local "Research KXRAINNYC-26MAY31-T0"

# Historical resolved-market backtest (signed Kalshi API)
uv run polybot backtest --tickers KXRAINNYC-26MAY28-T0

# Dry-run / place fake-money demo order from the promoted autoresearch strategy
uv run polybot demo-trade --ticker KXRAINNYC-26MAY31-T0
uv run polybot demo-trade --ticker KXRAINNYC-26MAY31-T0 --place-order

# Strategy autoresearch (mock or Codex)
uv run polybot loop --worker mock --iterations 1
uv run polybot loop --worker codex --iterations 1 --codex-app-name polybot

# Modal fan-out (use package module paths)
uv run modal run kalshi_agent/research/modal_app.py --tickers KXRAINNYC-26MAY31-T0
```

## Kalshi and data-source APIs (keep these)

| Module | Role |
|--------|------|
| `kalshi_agent/kalshi_public.py` | Unsigned market + orderbook reads for research memos |
| `kalshi_agent/kalshi_client.py` | Minimal **signed** RSA client for balance/markets smoke tests |
| `kalshi_agent/transport.py` | Production HTTP layer: signing, retries, rate limits |
| `kalshi_agent/datasource.py` | `RestDataSource` / `WebSocketDataSource` → `MarketState` |
| `kalshi_agent/weather.py` | Open-Meteo + NWS helpers for the live `run` demo |
| `kalshi_agent/research/core.py` | Weather research pipeline (Kalshi public + NWS + paper decision) |
| `kalshi_agent/history.py` | Fetch Kalshi candlesticks + settlement and replay `MarketState`s |
| `kalshi_agent/backtest.py` | Real resolved-market backtest through live strategy/risk/paper path |
| `kalshi_agent/metrics.py` | PnL, win rate, Brier, and Kalshi fee scoring helpers |
| `kalshi_agent/demo_trade.py` | Run promoted autoresearch strategies against Kalshi demo/prod plumbing |

Research uses **public** endpoints (no key). Live paper/demo trading uses **transport** + optional keys in `.env.local`.

## Two strategy systems (intentional)

| Path | Contract | Used by |
|------|----------|---------|
| `kalshi_agent/strategy.py` + `kalshi_agent/types.py` | Prices in **cents**, `fair_prob_yes` | `polybot run`, `polybot backtest`, `kalshi_agent.smoke`, tests |
| `kalshi_agent/autoresearch/baseline.py` + `types.py` | Prices as **0–1 floats**, `model_probability_yes` | `polybot loop`, Codex worker, frozen `backtest.py` |

Do not merge these types; autoresearch candidates import `kalshi_agent.autoresearch.types`.

## Package map

```
kalshi_agent/
  cli.py              # polybot <command>
  run.py              # DataSource → strategy → risk → executor demo
  smoke.py            # Live Kalshi demo REST + WS + optional order
  read_cli.py         # Signed read smoke test
  kalshi_client.py    # Minimal signed client
  kalshi_public.py    # Unsigned research reads
  transport.py        # Full signed HTTP
  datasource.py       # MarketState producers
  weather.py          # External forecast APIs
  history.py          # Candles + settlement -> replay stream
  backtest.py         # Resolved-market live-path backtester
  metrics.py          # Backtest scorecard helpers
  demo_trade.py       # Promoted strategy -> demo LiveExecutor
  research/           # Weather memos, Modal fan-out, OpenAI agent
  autoresearch/       # Codex loop, backtest, registry, Modal scoring
```

Runtime artifacts (gitignored): `strategies/`, `ledger.jsonl`, `strategy_ledger.jsonl`, `outputs/`.

## Removed from repo root

These were duplicate shims; use `polybot` or `uv run -m kalshi_agent.<module>` instead:

- `loop.py`, `research.py`, `backtest.py`, `evaluator.py`, `strategy_registry.py`
- `codex_worker.py`, `agent_runner.py`, `strategy.py`, `strategy_types.py`
- `modal_app.py`, `modal_strategy_app.py`, `modal_sandbox_smoke.py`
