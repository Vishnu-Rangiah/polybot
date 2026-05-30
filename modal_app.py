from __future__ import annotations

import json
from collections.abc import Iterable

import modal

from research import append_ledger_entry

app = modal.App("polybot-kalshi-research")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("requests")
    .add_local_python_source("research")
)


@app.function(image=image, timeout=120)
def research_one_market(ticker: str) -> dict:
    from research import research_market

    return research_market(ticker)


def parse_tickers(tickers: str | Iterable[str]) -> list[str]:
    if isinstance(tickers, str):
        candidates = tickers.split(",")
    else:
        candidates = tickers
    return [ticker.strip().upper() for ticker in candidates if ticker and ticker.strip()]


def research_many_markets(tickers: str | Iterable[str], *, manage_app: bool = True) -> list[dict]:
    ticker_list = parse_tickers(tickers)
    if not ticker_list:
        raise ValueError("At least one ticker is required.")

    if not manage_app:
        return list(research_one_market.map(ticker_list))

    with app.run():
        return list(research_one_market.map(ticker_list))


@app.local_entrypoint()
def main(tickers: str, write_ledger: bool = True) -> None:
    results = research_many_markets(tickers, manage_app=False)
    for result in results:
        if write_ledger:
            append_ledger_entry(result, run_type="modal_weather_research")
        print(json.dumps(result, indent=2, sort_keys=True))
