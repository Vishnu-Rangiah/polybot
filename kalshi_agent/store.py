"""Append-only snapshot log.

Every `MarketState` the bot observes live gets written here with its timestamp.
That single habit gives you backtest data for free: historical replay is just
reading this log back in `observed_at_ms` order. Live ingestion and historical
ingestion become the same data, recorded once.

JSONL (one JSON object per line) is chosen deliberately: append-only, survives a
crash mid-write (you lose at most the last line), and is trivially streamable
without loading the whole file.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Iterator

from kalshi_agent.types import MarketState


class SnapshotStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, state: MarketState) -> None:
        record = dataclasses.asdict(state)
        with self.path.open("a") as f:
            f.write(json.dumps(record) + "\n")

    def replay(self) -> Iterator[MarketState]:
        """Yield snapshots in recorded order. The backtester's input."""
        if not self.path.exists():
            return
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    yield MarketState(**json.loads(line))
