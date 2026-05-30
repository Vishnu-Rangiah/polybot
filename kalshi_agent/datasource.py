"""DataSource: the interface that produces `MarketState`.

`get_state(ticker)` is the whole contract. Any implementation — live REST,
websocket, or historical replay — satisfies it, and the strategy can't tell them
apart. That interchangeability is the design's payoff: the same strategy runs in
production, on a paper feed, and over recorded history with zero changes.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Iterable, Protocol, runtime_checkable

from kalshi_agent.normalize import normalize, parse_levels, price_to_cents
from kalshi_agent.transport import Transport
from kalshi_agent.types import MarketState


@runtime_checkable
class DataSource(Protocol):
    def get_state(self, ticker: str, *, features: dict | None = None) -> MarketState:
        """Return the latest normalized snapshot for one market."""
        ...


class RestDataSource:
    """Polls Kalshi's REST endpoints and normalizes the result.

    Right for startup, sanity checks, and low-frequency markets. For real-time
    trading you'd add a `WebSocketDataSource` implementing the same Protocol —
    the strategy and executor wouldn't notice the swap.
    """

    def __init__(self, transport: Transport, *, orderbook_depth: int = 5):
        self._t = transport
        self._depth = orderbook_depth

    def get_state(self, ticker: str, *, features: dict | None = None) -> MarketState:
        # Stamp observation time at fetch, before any processing — this is the
        # timestamp backtests treat as "now" for no-lookahead enforcement.
        observed_at_ms = int(time.time() * 1000)
        market = self._t.get(f"/markets/{ticker}")["market"]
        resp = self._t.get(f"/markets/{ticker}/orderbook", params={"depth": self._depth})
        # Live API returns `orderbook_fp`; older shape used `orderbook`.
        book = resp.get("orderbook_fp") or resp.get("orderbook") or {}
        return normalize(market, book, observed_at_ms=observed_at_ms, features=features)


class WebSocketDataSource:
    """Real-time data via Kalshi's WebSocket feed, behind the same pull interface.

    This is where the design pays off. The feed is *push*: Kalshi sends one
    `orderbook_snapshot` per market, then a stream of incremental
    `orderbook_delta` messages. A background thread folds those into an in-memory
    book; `get_state` simply reads the current best levels and normalizes them.
    The strategy calls `get_state(ticker)` exactly as it would on `RestDataSource`
    and never learns the data arrived as a delta stream.

    Book maintenance (the testable core) is deliberately separated from the
    socket: `_handle` processes a parsed message and is exercised directly in
    tests without any network.
    """

    def __init__(self, transport: Transport, tickers: Iterable[str],
                 *, channels: Iterable[str] = ("orderbook_delta",)):
        self._t = transport
        self._tickers = list(tickers)
        self._channels = list(channels)
        # ticker -> {"yes": {price_cents: qty}, "no": {price_cents: qty}}
        self._books: dict[str, dict[str, dict[int, int]]] = {}
        self._lock = threading.Lock()
        self._ready = threading.Event()  # set on first snapshot / subscribe ack
        self._ws = None
        self._thread: threading.Thread | None = None

    # --- lifecycle -----------------------------------------------------------

    def start(self, *, timeout_s: float = 10.0) -> "WebSocketDataSource":
        import websocket  # lazy: only needed for live streaming

        headers = [f"{k}: {v}" for k, v in self._t.ws_auth_headers().items()]
        self._ws = websocket.WebSocketApp(
            self._t.ws_url(),
            header=headers,
            on_open=self._on_open,
            on_message=lambda _ws, raw: self._handle(json.loads(raw)),
            on_close=lambda *_: self._ready.clear(),
        )
        self._thread = threading.Thread(target=self._ws.run_forever, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout_s):
            raise TimeoutError("websocket did not become ready in time")
        return self

    def close(self) -> None:
        if self._ws is not None:
            self._ws.close()

    def __enter__(self) -> "WebSocketDataSource":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()

    # --- subscription + message handling ------------------------------------

    def _on_open(self, ws) -> None:
        # One subscribe per ticker (params take a single `market_ticker`).
        for i, ticker in enumerate(self._tickers, start=1):
            ws.send(json.dumps({
                "id": i,
                "cmd": "subscribe",
                "params": {"channels": self._channels, "market_ticker": ticker},
            }))

    def _handle(self, msg: dict) -> None:
        """Process one parsed feed message. Pure w.r.t. the socket — tests call
        this directly with synthetic snapshots/deltas."""
        mtype = msg.get("type")
        if mtype == "subscribed":
            return  # ack only; readiness waits for the snapshot (below)

        body = msg.get("msg", {})
        ticker = body.get("market_ticker") or body.get("market_id")
        if ticker is None:
            return

        if mtype == "orderbook_snapshot":
            # Reuse the REST level parser so both feeds agree on cents, and
            # accept every key variant (`yes`, `yes_dollars`, `yes_dollars_fp`).
            with self._lock:
                self._books[ticker] = {
                    "yes": dict(parse_levels(body, "yes")),
                    "no": dict(parse_levels(body, "no")),
                }
            self._ready.set()  # only a real snapshot means the book is usable
        elif mtype == "orderbook_delta":
            self._apply_delta(ticker, body)

    def _apply_delta(self, ticker: str, body: dict) -> None:
        side = body["side"]
        # WS uses price_dollars/delta_fp; tolerate older price/delta too.
        price = price_to_cents(body.get("price_dollars", body.get("price")))
        delta = round(float(body.get("delta_fp", body.get("delta"))))
        with self._lock:
            book = self._books.setdefault(ticker, {"yes": {}, "no": {}})
            level = book[side]
            level[price] = level.get(price, 0) + delta
            if level[price] <= 0:
                level.pop(price, None)  # a level at zero contracts is gone

    # --- DataSource interface ------------------------------------------------

    def get_state(self, ticker: str, *, features: dict | None = None) -> MarketState:
        with self._lock:
            book = self._books.get(ticker)
            if book is None:
                raise KeyError(f"no orderbook received yet for {ticker!r}")
            orderbook = {
                "yes": [[p, q] for p, q in book["yes"].items()],
                "no": [[p, q] for p, q in book["no"].items()],
            }
        observed_at_ms = int(time.time() * 1000)
        return normalize(
            {"ticker": ticker}, orderbook,
            observed_at_ms=observed_at_ms, features=features,
        )
