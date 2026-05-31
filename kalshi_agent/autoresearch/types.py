from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Side = Literal["yes", "no"]


@dataclass(frozen=True)
class MarketState:
    """Point-in-time market snapshot visible to a strategy."""

    ticker: str
    timestamp_utc: str
    title: str | None = None
    series_ticker: str | None = None
    category: str | None = None
    yes_bid: float | None = None
    yes_ask: float | None = None
    no_bid: float | None = None
    no_ask: float | None = None
    volume: float | None = None
    liquidity: float = 0.0
    time_to_close_seconds: float | None = None
    features: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MarketState":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Order:
    side: Side
    size: int
    limit_price: float

    def __post_init__(self) -> None:
        if self.size <= 0:
            raise ValueError("Order size must be positive.")
        if not 0.0 <= self.limit_price <= 1.0:
            raise ValueError("Order limit_price must be between 0 and 1.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Metrics:
    pnl: float
    sharpe: float
    brier: float | None
    n_trades: int
    max_dd: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
