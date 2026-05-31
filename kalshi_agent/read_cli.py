"""Smoke test: signed Kalshi read requests using credentials from .env.local."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from kalshi_agent.kalshi_client import DEMO_BASE, PROD_BASE, KalshiClient


def load_env_local(path: str = ".env.local") -> None:
    env_path = Path.cwd() / path
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_env_local()

    key_id = os.environ.get("KALSHI_KEY_ID")
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
    base = DEMO_BASE if os.environ.get("KALSHI_ENV") == "demo" else PROD_BASE

    if not key_id or not key_path:
        print("Missing KALSHI_KEY_ID or KALSHI_PRIVATE_KEY_PATH in .env.local", file=sys.stderr)
        return 1

    client = KalshiClient(key_id=key_id, private_key_path=key_path, base_url=base)
    print(f"→ {base}\n")

    balance = client.balance()
    print(f"✅ Auth OK. Balance: ${balance['balance'] / 100:,.2f}")

    markets = client.markets(limit=5)
    print(f"\nSample of {len(markets.get('markets', []))} open markets:")
    for market in markets.get("markets", []):
        yes = market.get("yes_bid")
        print(f"  • {market['ticker']:<22} yes_bid={yes}¢  {market.get('title', '')[:50]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
