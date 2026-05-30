"""kalshi_agent — a layered Kalshi trading system.

The whole design rests on two narrow interfaces and one shared contract:

    DataSource  ── produces ──▶  MarketState   (kalshi_agent.types)
    Executor    ── consumes ──▶  Order         (kalshi_agent.types)

Everything above these (strategy, risk, research agent) speaks only `MarketState`
and `Order`, never raw Kalshi JSON. That is what makes live / paper / backtest
three swappable implementations of the same two interfaces.

Layers, low to high:

    transport.py   signing + HTTP + retry/rate-limit   (the only thing that knows about `requests`)
    normalize.py   raw Kalshi JSON -> MarketState       (the only place wire quirks live)
    datasource.py  DataSource protocol + REST poller
    store.py       append-only snapshot log (= backtest data, for free)
    risk.py        pre-trade gate (limits, kill-switch)
    executor.py    Executor protocol + Paper / Live impls
    strategy.py    decide(state) -> Order | None
"""

from kalshi_agent.types import (
    Fill,
    MarketState,
    Order,
    OrderAction,
    Position,
    Side,
)

__all__ = [
    "Fill",
    "MarketState",
    "Order",
    "OrderAction",
    "Position",
    "Side",
]
